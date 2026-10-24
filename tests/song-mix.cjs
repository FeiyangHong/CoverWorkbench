const assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const [base,song,voice]=process.argv.slice(2);assert(base&&song&&voice);
 const browser=await chromium.launch({headless:true,channel:process.env.CW_BROWSER_CHANNEL||'msedge'});
 try{
  const page=await browser.newPage({viewport:{width:1550,height:1150}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/mix-guide/index.html');
  await page.locator('#mgSongMode').selectOption('song');
  await page.locator('#mgSongPath').fill('"'+song+'"');
  await page.locator('#mgSongRead').click();
  await page.waitForFunction(()=>document.querySelector('#mgSongProfileNote').textContent.includes('已核验'),null,{timeout:130000});
  assert(await page.locator('#mgNativeControls').isHidden());
  assert((await page.locator('#mgSongBacking').inputValue()).endsWith('.wav'));
  const mix=await page.locator('[data-song-key="mix"]').inputValue();assert.equal(Number(mix),100,'FX-return wet ratio must come from the saved Song');
  await page.locator('#mgNativePath').fill(voice);await page.locator('#mgNativeStart').fill('0:35');await page.locator('#mgNativeEnd').fill('0:39');
  await page.locator('[data-song-key="space"]').fill('1.2');
  await page.locator('#mgNativeRender').click();
  await page.waitForFunction(()=>!document.querySelector('#mgNativePlayer').hidden,null,{timeout:240000});
  assert((await page.locator('#mgNativeEvidence').innerText()).includes('静态混音'));
  assert((await page.locator('#mgNativeEvidence').innerText()).includes('100%'));
  await page.locator('#mgNativePlay').click();await page.waitForFunction(()=>Number(document.querySelector('#mgNativeSeek').value)>.25);
  const before=Number(await page.locator('#mgNativeSeek').inputValue());await page.locator('[data-mg-native-ab="a"]').click();assert(Number(await page.locator('#mgNativeSeek').inputValue())>=before-.05);
  await page.locator('#mgNativePlay').click();
  await page.locator('#mgNative').screenshot({path:'work/song-mix-preview.png'});
  await page.locator('.mg-song-extra summary').click();await page.locator('#mgSongExtraAdd').click();assert.equal(await page.locator('.mg-song-extra-row').count(),1);await page.locator('[data-extra-remove]').click();
  await page.locator('#mgSongTarget').selectOption({label:await page.locator('#mgSongTarget option').filter({hasText:'Pro-Q 3'}).first().innerText()});
  await page.waitForFunction(()=>!document.querySelector('#mgSongBandLabel').hidden,null,{timeout:130000});
  assert(await page.locator('#mgSongBand option').count()>0);
  await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  assert.deepEqual(errors,[]);console.log('PASS: saved Song selection, restored 100% wet state, backing recommendation, real full-chain A/B, extra stems, EQ bands and mobile layout');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
