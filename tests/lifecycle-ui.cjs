const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const base=process.argv[2];assert(base);
 const browser=await chromium.launch({headless:true,...(process.env.CW_BROWSER_CHANNEL?{channel:process.env.CW_BROWSER_CHANNEL}:{})});
 try{
  const context=await browser.newContext({viewport:{width:1360,height:950}}),page=await context.newPage(),guide=await context.newPage();
  const errors=[];for(const tab of [page,guide])tab.on('pageerror',e=>errors.push(e.message));
  await page.goto(base);await page.locator('#cwExitButton').click();
  await page.locator('#cwExitActivity').filter({hasText:'后台空闲'}).waitFor();
  await page.locator('#cwExitCancel').click();assert(!(await page.locator('#cwExitDialog').isVisible()));
  assert((await (await context.request.get(base+'/api/health')).json()).ok);
  await guide.goto(base+'/mix-guide/index.html');
  await guide.locator('#mgDemoPlay').click();
  await guide.waitForFunction(()=>document.querySelector('#mgDemoPlay').textContent.includes('暂停'));
  await guide.locator('#cwExitButton').click();await guide.locator('#cwExitActivity').filter({hasText:'后台空闲'}).waitFor();
  await guide.setViewportSize({width:390,height:844});assert(await guide.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  // Check that the UI does not force an exit if a task appears after confirmation was opened.
  await guide.route('**/api/lifecycle',route=>route.fulfill({json:{instance:'test',state:'running',canExit:false,auditions:1,deliveries:0,operations:{}}}));
  await guide.locator('#cwExitActivity').filter({hasText:'1 个试听任务'}).waitFor();assert(await guide.locator('#cwExitConfirm').isDisabled());
  await guide.unroute('**/api/lifecycle');await guide.locator('#cwExitActivity').filter({hasText:'后台空闲'}).waitFor();
  await guide.locator('#cwExitConfirm').click();
  await guide.locator('#cwExitScreenTitle').filter({hasText:'工作台已彻底退出'}).waitFor({timeout:15000});
  await page.locator('#cwExitScreenTitle').filter({hasText:'工作台已彻底退出'}).waitFor({timeout:15000});
  assert(!(await guide.locator('#mgDemoPlay').innerText()).includes('暂停'),'Exit must stop decoded browser audio');
  assert(await guide.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await guide.locator('#cwReconnect').click();assert((await guide.locator('#cwExitScreenStatus').innerText()).includes('尚未重新启动'));
  assert.deepEqual(errors,[]);console.log('PASS: main/standalone exit entry, cancel, busy UI, mobile layout, confirmed real shutdown, cross-tab notice, audio stop and restart guidance');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
