const assert = require('node:assert/strict');

module.exports = async function verifyMixAudio(page) {
  await page.waitForFunction(() => window.CWMixAudio && !document.querySelector('#mgDemoPlay').disabled);
  const metrics = await page.evaluate(async () => {
    const api = window.CWMixAudio, clip = api.synthetic('vowel');
    const dry = await api.effect(clip, 'dry', {});
    const output = {};
    for (const [name, values] of [
      ['reverb', {decay: 1.4, wet: .35, predelay: 30}],
      ['delay', {time: 375, feedback: .3, wet: .35}],
      ['eq', {freq: 700, gain: -9, q: 1}]
    ]) {
      const processed = await api.effect(clip, name, values);
      const gains = api.levels(dry, processed, true);
      const a = dry.getChannelData(0), b = processed.getChannelData(0);
      let difference = 0, tail = 0;
      for (let i = 0; i < a.length; i++) {
        difference += (a[i] * gains.a - b[i] * gains.b) ** 2;
        if (i > 6.5 * dry.sampleRate) tail += b[i] ** 2;
      }
      const am = api.measure(dry), bm = api.measure(processed);
      output[name] = {duration: processed.duration, difference: Math.sqrt(difference / a.length),
        peak: gains.peak, tail, levelDifference: Math.abs(am.rms * gains.a - bm.rms * gains.b)};
    }
    return output;
  });
  for (const name of ['reverb', 'delay', 'eq']) {
    const value = metrics[name];
    assert.equal(value.duration, 12);
    assert(value.difference > .0001, `${name} must change the signal`);
    assert(value.peak <= .881, `${name} must retain peak headroom`);
    assert(value.levelDifference < .00001, `${name} A/B RMS matching`);
  }
  assert(metrics.reverb.tail > .001, 'Reverb must have a tail');
  assert(metrics.delay.tail > .001, 'Delay must have repetitions after the source stops');
  await page.locator('#mgDemoPlay').click();
  await page.waitForFunction(() => document.querySelector('#mgDemoPlay').textContent.includes('暂停'));
  await page.waitForFunction(() => Number(document.querySelector('#mgDemoSeek').value) > .3);
  const before = await page.locator('#mgDemoSeek').inputValue();
  await page.locator('[data-mg-ab="a"]').click();
  assert.equal(await page.locator('[data-mg-ab="a"]').getAttribute('aria-pressed'), 'true');
  const after = await page.locator('#mgDemoSeek').inputValue();
  assert(Number(after) >= Number(before) - .05, 'A/B switch must preserve the timeline');
  await page.locator('#mgDemoPlay').click();
  const paused = await page.locator('#mgDemoSeek').inputValue();
  await page.locator('[data-mg-ab="b"]').click();
  assert.equal(await page.locator('#mgDemoSeek').inputValue(), paused, 'Paused A/B switch must not seek');
  await page.locator('#mgDemoStop').click();
  assert.equal(Number(await page.locator('#mgDemoSeek').inputValue()), 0);
  await page.locator('#mgDemoType').selectOption('eq');
  await page.waitForFunction(() => document.querySelector('#mgDemoStatus').textContent.includes('共用时间线'));
  await page.locator('[data-mg-demo-control="gain"]').fill('-9');
  assert((await page.locator('#mgDemoValue-gain').innerText()).includes('-9'));
  await page.locator('[data-mg-goal="air"]').click();
  assert.equal(await page.locator('#mgDemoShape').inputValue(), 'highshelf');
  assert.equal(await page.locator('[data-mg-demo-control="freq"]').inputValue(), '10000');
  assert(await page.locator('[data-mg-demo-control="q"]').isDisabled());
  await page.locator('[data-mg-goal="mud"]').click();
  assert.equal(await page.locator('#mgDemoShape').inputValue(), 'peaking');
  assert.equal(await page.locator('[data-mg-demo-control="freq"]').inputValue(), '350');
  await page.locator('#mgDemoSource').selectOption('pluck');
  await page.waitForFunction(() => document.querySelector('#mgDemoStatus').textContent.includes('合成拨弦'));
  // Decode a locally selected synthetic file entirely in the browser.
  const rate = 16000, frames = rate, wav = Buffer.alloc(44 + frames * 2);
  wav.write('RIFF', 0); wav.writeUInt32LE(wav.length - 8, 4); wav.write('WAVEfmt ', 8);
  wav.writeUInt32LE(16, 16); wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22);
  wav.writeUInt32LE(rate, 24); wav.writeUInt32LE(rate * 2, 28); wav.writeUInt16LE(2, 32);
  wav.writeUInt16LE(16, 34); wav.write('data', 36); wav.writeUInt32LE(frames * 2, 40);
  for (let index = 0; index < frames; index++) wav.writeInt16LE(Math.round(Math.sin(index / rate * 2 * Math.PI * 440) * 5000), 44 + index * 2);
  const outgoing = [];
  const watch = request => {if (request.method() !== 'GET') outgoing.push(request.url());};
  page.on('request', watch);
  await page.locator('#mgDemoFile').setInputFiles({name: 'original-test.wav', mimeType: 'audio/wav', buffer: wav});
  await page.waitForFunction(() => document.querySelector('#mgDemoStatus').textContent.includes('本地音频'));
  assert((await page.locator('#mgDemoStatus').innerText()).includes('5.0 秒'), 'Local sample must be decoded/resampled before processing');
  assert.deepEqual(outgoing, [], 'Local audio must never be uploaded');
  page.off('request', watch);
  await page.setViewportSize({width: 2560, height: 1440});
  await page.locator('[data-mg-view="photo"]').click();
  await page.locator('#mgImage img').evaluate(image => image.decode());
  const size = await page.locator('#mgImage img').evaluate(image => ({width: image.getBoundingClientRect().width, natural: image.naturalWidth}));
  assert(size.width <= size.natural + 1, 'Large viewport must not stretch the screenshot');
  console.log('PASS: non-silent reverb/delay/EQ differences, tail energy, RMS matching/headroom, A/B timeline, transport and source controls');
};
