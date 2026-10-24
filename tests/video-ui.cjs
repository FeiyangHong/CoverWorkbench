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
  await page.locator('[data-step="mv"]').waitFor();
  if(await page.locator('[data-step]').count()!==6)throw Error('Six-step guide missing');
  await page.locator('[data-step="mv"]').click();await page.getByText('下载并使用 MV，或选择存在的本地视频',{exact:true}).waitFor();
  await page.locator('#add').click();await page.locator('[data-cue$=":original"]').fill('A synthetic line');
  await page.locator('#save').click();await page.locator('#dirty').filter({hasText:'已保存'}).waitFor();
  await page.locator('[data-panel="layout"]').click();await page.locator('[data-style="global:original:size"]').fill('42');await page.locator('#save').click();
  await page.locator('#dirty').filter({hasText:'已保存'}).waitFor();await page.reload();await page.locator('#name').filter({hasText:'Synthetic Video'}).waitFor();
  if(await page.locator('[data-cue$=":original"]').inputValue()!=='A synthetic line')throw Error('Subtitle edit lost');
  await page.locator('[data-panel="layout"]').click();if(await page.locator('[data-style="global:original:size"]').inputValue()!=='42')throw Error('Style edit lost');
  await page.locator('[data-font-browse="global:original"]').click();
  await page.locator('#fontPreviewDialog').waitFor();
  if(!(await page.locator('#fontSpecimens').innerText()).includes('微软雅黑')||!(await page.locator('#fontSpecimens').innerText()).includes('黑体'))throw Error('Chinese font labels missing');
  await page.locator('#fontSample').fill('中文字体预览 Aa 123');
  await page.locator('#fontSpecimens .font-specimen:not([disabled])').first().click();
  await page.locator('#fontPreviewDialog').waitFor({state:'hidden'});
  await page.locator('[data-cue$=":translation"]').fill('字幕预览示例');
  await page.locator('.lane-translation [data-caption]').waitFor();
  await page.locator('#captionZoom').selectOption('4');
  if(!await page.locator('#captionScroll').evaluate(el=>el.scrollWidth>el.clientWidth*2))throw Error('Timeline zoom missing');
  const block=page.locator('.lane-original [data-caption]').first();await block.scrollIntoViewIfNeeded();
  await page.locator('#captionScroll').evaluate(el=>el.scrollLeft=0);
  const box=await block.boundingBox();await page.mouse.move(box.x+22,box.y+12);await page.mouse.down();await page.mouse.move(box.x+82,box.y+12,{steps:5});await page.mouse.up();
  if(Number(await page.locator('[data-cue$=":start"]').inputValue())<=0)throw Error('Caption drag did not change time');
  await page.locator('#save').click();await page.locator('#dirty').filter({hasText:'已保存'}).waitFor();
  await page.setViewportSize({width:390,height:844});await page.waitForTimeout(100);
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2))throw Error('Mobile overflow');
  await page.locator('#cwExitButton').click();await page.locator('#cwExitActivity').filter({hasText:'空闲'}).waitFor();await page.locator('#cwExitCancel').click();
  if(errors.length)throw Error(errors.join('\n'));
  console.log('PASS: six-step missing checks, Chinese font specimens, dual caption lanes, zoom/drag, text/style persistence, mobile layout and shared exit controls');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
