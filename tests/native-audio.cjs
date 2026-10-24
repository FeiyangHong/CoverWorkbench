/* Run against a local test server with an explicitly chosen local vocal path. */
const assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const [base,input]=process.argv.slice(2);assert(base&&input,'Usage: node tests/native-audio.cjs URL AUDIO_PATH');
 const browser=await chromium.launch({headless:true,channel:process.env.CW_BROWSER_CHANNEL||'msedge'});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/mix-guide/index.html');
  await page.waitForFunction(()=>document.querySelector('#mgNativeEnvironment').textContent.includes('已就绪'));
  await page.locator('#mgNativePath').fill('"'+input+'"');
  await page.locator('#mgNativeInspect').click();
  await page.waitForFunction(()=>document.querySelector('#mgNativeSourceInfo').textContent.includes('声道'));
  await page.locator('#mgNativeBrowse').click();
  await page.locator('.mg-native-entry').first().waitFor();
  await page.locator('#mgNativeSort').selectOption('name-asc');
  await page.keyboard.press('Escape');
  await page.locator('#mgNativeStart').fill('0:35');
  await page.locator('#mgNativeEnd').fill('0:39');
  for(const plugin of ['reverb','delay','eq']){
   await page.locator('#mgNativePlugin').selectOption(plugin);
   await page.locator('#mgNativeRender').click();
   await page.waitForFunction(()=>!document.querySelector('#mgNativePlayer').hidden,{},{timeout:130000});
   assert((await page.locator('#mgNativeStatus').innerText()).includes('真实 VST3'));
   await page.locator('#mgNativePlay').click();
   await page.waitForFunction(()=>Number(document.querySelector('#mgNativeSeek').value)>.3);
   const before=Number(await page.locator('#mgNativeSeek').inputValue());
   await page.locator('[data-mg-native-ab="a"]').click();
   assert(Number(await page.locator('#mgNativeSeek').inputValue())>=before-.05);
   await page.locator('#mgNativePlay').click();
   const paused=await page.locator('#mgNativeSeek').inputValue();
   await page.locator('[data-mg-native-ab="b"]').click();
   assert.equal(await page.locator('#mgNativeSeek').inputValue(),paused);
  }
  await page.locator('#mgDemoPlay').click();
  assert((await page.locator('#mgNativePlay').innerText()).includes('播放'),'Generic and native player must not overlap');
  await page.locator('#mgDemoPlay').click();
  await page.locator('#mgNativePlay').click();
  await page.locator('[data-mg-native-control="gain"]').fill('-8');
  assert(await page.locator('#mgNativePlayer').isHidden(),'Edited parameters must invalidate old audio');
  await page.setViewportSize({width:390,height:844});
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await page.setViewportSize({width:1440,height:1100});
  await page.locator('#mgNative').screenshot({path:'work/native-audio-preview.png'});
  assert.deepEqual(errors,[]);
  console.log('PASS: real-plugin source/interval UI, file browser, three renders, A/B continuity/pause, edit invalidation and mobile layout');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
