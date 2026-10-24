/* Empty-install browser coverage; no private media, network download or FFmpeg needed. */
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.CW_BROWSER_CHANNEL?{channel:process.env.CW_BROWSER_CHANNEL}:{})});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1100}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(process.argv[2]+'/video/index.html');
  await page.locator('#environment').filter({hasText:'本机处理'}).waitFor();
  await page.locator('#new').click();await page.locator('#newName').fill('Synthetic Video');await page.locator('#promptForm button[type=submit]').click();
  await page.locator('#name').filter({hasText:'Synthetic Video'}).waitFor();
  await page.locator('#add').click();await page.locator('[data-cue$=":original"]').fill('A synthetic line');
  await page.locator('#save').click();await page.locator('#dirty').filter({hasText:'已保存'}).waitFor();
  await page.locator('[data-panel="layout"]').click();await page.locator('[data-style="global:original:size"]').fill('42');await page.locator('#save').click();
  await page.locator('#dirty').filter({hasText:'已保存'}).waitFor();await page.reload();await page.locator('#name').filter({hasText:'Synthetic Video'}).waitFor();
  if(await page.locator('[data-cue$=":original"]').inputValue()!=='A synthetic line')throw Error('Subtitle edit lost');
  await page.locator('[data-panel="layout"]').click();if(await page.locator('[data-style="global:original:size"]').inputValue()!=='42')throw Error('Style edit lost');
  await page.setViewportSize({width:390,height:844});await page.waitForTimeout(100);
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2))throw Error('Mobile overflow');
  await page.locator('#cwExitButton').click();await page.locator('#cwExitActivity').filter({hasText:'空闲'}).waitFor();await page.locator('#cwExitCancel').click();
  if(errors.length)throw Error(errors.join('\n'));
  console.log('PASS: Video Studio create, text/style persistence, reload, mobile layout and shared exit controls');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
