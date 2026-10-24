const assert = require('node:assert/strict');

module.exports = async function verifyMixGuide(page, base) {
  const writes = [];
  const watch = request => {if (request.method() !== 'GET') writes.push(request.url());};
  page.on('request', watch);
  try {
    const tab = page.locator('[data-tab="mix-guide"]');
    assert.equal(await tab.isEnabled(), true, 'Guide must work before any project import');
    await tab.click();
    await page.locator('#mgAdvice h3').filter({hasText: '混响拖尾太长'}).waitFor();
    assert.equal(await page.locator('[data-mg-goal]').count(), 18);
    for (const id of ['routing', 'reverb', 'delay', 'eq', 'comp', 'deess']) {
      await page.locator(`[data-mg-plugin="${id}"]`).click();
      await page.locator('#mgImage img').evaluate(image => image.decode());
      assert(await page.locator('#mgImage img').evaluate(image => image.naturalWidth > 0));
      const control = page.locator('#mgImage [data-mg-point]').last();
      const controlId = await control.getAttribute('data-mg-point');
      await control.click();
      assert.equal(await page.locator(`#mgControls [data-mg-control="${controlId}"]`).getAttribute('aria-pressed'), 'true');
      assert((await page.locator('#mgControlDetail').innerText()).length > 30);
      await page.locator('[data-mg-view="photo"]').click();
      await page.locator('#mgImage img').evaluate(image => image.decode());
      const image = await page.locator('#mgImage img').evaluate(image => ({natural: image.naturalWidth, width: image.getBoundingClientRect().width, height: image.getBoundingClientRect().height}));
      assert(image.width <= image.natural + 1, 'Reference screenshot must not be upscaled');
      assert(image.height <= 340, 'Default reference should remain compact');
      await page.locator('[data-mg-view="clear"]').click();
    }
    await page.locator('#mgBackToGoal').click();
    assert.equal(await page.locator('[data-mg-plugin="reverb"]').getAttribute('aria-pressed'), 'true');
    await page.locator('[data-mg-category="delay"]').click();
    assert.equal(await page.locator('[data-mg-goal]').count(), 5);
    await page.locator('[data-mg-goal="noecho"]').click();
    assert((await page.locator('#mgAdvice').innerText()).includes('默认静音'));
    await page.locator('[data-mg-category="all"]').click();
    await page.locator('#mgSearch').fill('不存在的效果');
    assert.equal(await page.locator('[data-mg-goal]').count(), 0);
    assert(await page.locator('.mg-empty').isVisible());
    await page.locator('#mgSearch').fill('齿音');
    assert(await page.locator('[data-mg-goal="sibilance"]').isVisible());
    await page.locator('[data-mg-goal="sibilance"]').click();
    await page.locator('#mgZoom').click();
    await page.locator('#mgZoomDialog').waitFor();
    await page.locator('#mgZoomIn').click();
    assert.equal(await page.locator('#mgZoomValue').innerText(), '125%');
    await page.locator('#mgZoomImage [data-mg-point="range"]').click();
    assert((await page.locator('#mgZoomDetail').innerText()).includes('最多减轻'));
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#mgZoomDialog').isVisible(), false);
    assert.equal(await page.evaluate(() => document.activeElement.id), 'mgZoom');
    await page.setViewportSize({width: 390, height: 844});
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
    await page.locator('#mgZoom').click();
    await page.locator('#mgZoomIn').click();
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
    await page.keyboard.press('Escape');
    await page.setViewportSize({width: 1360, height: 950});
    assert.deepEqual(writes, [], 'Guide interactions must not mutate project or DAW state');
  } finally {
    page.off('request', watch);
  }
  const standalone = await page.context().browser().newPage();
  try {
    const errors = [];
    standalone.on('pageerror', error => errors.push(error.message));
    await standalone.goto(base + '/mix-guide/index.html');
    await standalone.waitForFunction(() => !document.querySelector('#mgNativeEnvironment').textContent.includes('正在检查'));
    assert(await standalone.locator('#mgNative').isVisible(), 'Native auditions must be available without importing a project');
    assert(await standalone.locator('#mgNativeRender').isDisabled(), 'A clean installation must report missing optional tools rather than emulate a native plugin');
    await standalone.locator('#mgSongMode').selectOption('song');
    assert(await standalone.locator('#mgSongSetup').isVisible());
    assert(await standalone.locator('#mgNativeRender').isDisabled(), 'Song mode requires an inspected and supported snapshot');
    await standalone.locator('#mgSongMode').selectOption('single');
    await standalone.locator('#mgImage img').evaluate(image => image.decode());
    assert.equal(await standalone.locator('[data-mg-goal]').count(), 18);
    await require('./mix-audio.cjs')(standalone);
    assert.deepEqual(errors, []);
  } finally {
    await standalone.close();
  }
  console.log('PASS: project-free mixing guide, six diagrams, control selection, search/filter, zoom/keyboard/mobile, no project writes');
};
