const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.CW_BROWSER_CHANNEL?{channel:process.env.CW_BROWSER_CHANNEL}:{})});
 try{
  const page=await browser.newPage({viewport:{width:1360,height:950}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto(process.argv[2]);await page.locator('#emptyWelcome').waitFor();
  assert.equal(await page.locator('#title').innerText(),'从你的第一首作品开始');
  await page.locator('#environmentSettings').click();await page.locator('#environmentStatus').filter({hasText:'Python'}).waitFor();
  await page.locator('#closeEnvironment').click();
  await page.locator('#welcomeImport').click();
  await page.locator('#importProjectForm [name=svp]').fill('"'+process.argv[3]+'"');
  await page.locator('#importProjectForm [name=title]').fill('My First Cover');
  await page.locator('#importProjectForm [name=language]').selectOption('en');
  await page.locator('#importProjectForm button[type=submit]').click();
  await page.waitForFunction(()=>document.querySelector('#title').textContent==='My First Cover'&&!document.querySelector('#importProjectDialog').open);
  assert.equal(await page.locator('#emptyWelcome').count(),0);
  await page.locator('[data-tab=lyrics]').click();
  await page.locator('[data-tab=daw]').click();
  await page.locator('#dawRecipe').filter({hasText:'Pro-Q 3'}).waitFor();
  await page.setViewportSize({width:390,height:844});
  await page.locator('#environmentSettings').click();
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),'Mobile document overflows');
  await page.screenshot({path:'reports/portable-mobile.png',fullPage:true});
  await page.locator('#closeEnvironment').click();
  await page.setViewportSize({width:1360,height:950});
  await page.screenshot({path:'reports/portable-desktop.png',fullPage:true});
  assert.deepEqual(errors,[]);console.log('PASS: fresh-install browser flow, no runtime errors');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
