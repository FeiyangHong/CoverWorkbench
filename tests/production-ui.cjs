/* Production-first navigation and handoffs; only a disposable clean server is used. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs/promises');
(async()=>{
 const base=process.argv[2],browser=await chromium.launch({headless:true,...(process.env.CW_BROWSER_CHANNEL?{channel:process.env.CW_BROWSER_CHANNEL}:{})});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  async function api(url,data){const response=await context.request[data===undefined?'get':'post'](base+url,data===undefined?{}:{data});const result=await response.json();assert.ok(response.ok(),JSON.stringify(result));return result;}
  const root=(await api('/api/health')).root;
  assert.ok(path.resolve(root).startsWith(path.resolve(__dirname,'../work')+path.sep)&&path.basename(root).startsWith('portable checkout '));
  const source=path.join(root,'input.svp'),original=await fs.readFile(source),audio=path.join(root,'final mix.wav');
  const project=await api('/api/project-import/new',{svp:source,title:'Production Demo',artist:'Synthetic artist',language:'en'});
  let liveRequests=0,launches=0,ready=false;
  page.on('request',r=>{if(r.url().includes('/api/live/'))liveRequests++;});
  await page.route('**/api/separation',r=>r.fulfill({json:{ready,reachable:ready,starting:false,url:base+'/msst-fixture',message:ready?'MSST 已就绪':'MSST 尚未启动',canLaunch:true,launcher:'C:\\Tools\\MSST\\webui.exe'}}));
  await page.route('**/api/separation-launch/local',r=>{launches++;ready=true;return r.fulfill({json:{message:'已请求启动 MSST'}});});
  await page.route('**/msst-fixture',r=>r.fulfill({contentType:'text/html',body:'<h1>MSST synthetic fixture</h1>'}));
  await page.goto(base);await page.locator('#projects [data-project="'+project.id+'"]').click();await page.locator('#title').filter({hasText:'Production Demo'}).waitFor();await page.locator('#productionSVState').filter({hasText:'已登记'}).waitFor();
  assert.equal(await page.locator('.production-stages article').count(),4);assert.ok(!await page.locator('[data-tab="review"]').isVisible());assert.ok(!await page.locator('[data-tab="compare"]').isVisible());assert.ok(!await page.locator('.live-strip').isVisible());assert.ok(!await page.locator('#legacyWorkflow').isVisible());assert.ok(!await page.locator('#deliveryTools').getAttribute('open'));
  await page.waitForTimeout(1800);assert.equal(liveRequests,0,'Native SV must not be polled in the normal workflow');
  await page.locator('#productionManage').click();await page.locator('#productionPath_mix').fill('"'+audio+'"');await page.locator('#productionPath_accompaniment').fill(audio);await page.locator('#productionAssetForm button[type=submit]').click();await page.locator('#productionAssetDialog').waitFor({state:'hidden'});
  await page.locator('#productionAssetList').filter({hasText:'final mix.wav'}).waitFor();assert.equal((await api('/api/music-video/'+project.id)).audio.path,audio);
  let openBody=null;await page.route('**/api/project-asset-open/*',async route=>{openBody=route.request().postDataJSON();await route.fulfill({json:{opened:true}});});
  await page.locator('[data-asset-open="svp"]').click();assert.equal(openBody.asset,'svp');assert.equal(openBody.action,'open');
  await page.locator('#productionBuildSong').click();assert.equal(await page.locator('#dawSVP').inputValue(),source);assert.equal(await page.locator('#dawAccompaniment').inputValue(),audio);assert.equal(await page.locator('#dawName').inputValue(),'Production Demo');
  await page.locator('[data-tab="lyrics"]').click();assert.ok(await page.locator('#lyricTools').isVisible());assert.ok(!await page.locator('.subtitle-table-wrap').isVisible());assert.ok(!await page.locator('#useLyricTiming').isVisible());
  await page.locator('[data-tab="separation"]').click();await page.locator('#msstStatus').filter({hasText:'尚未启动'}).waitFor();assert.equal(await page.locator('#msstEmbeddedFrame').count(),0);await page.locator('#msstLaunch').click();await page.locator('#msstBadge').filter({hasText:'已连接'}).waitFor();assert.equal(launches,1);
  await page.frameLocator('#msstEmbeddedFrame').getByRole('heading',{name:'MSST synthetic fixture'}).waitFor();await page.locator('#msstEmbeddedFrame').evaluate(e=>e.dataset.reused='yes');await page.locator('[data-tab="workflow"]').click();await page.locator('[data-tab="separation"]').click();await page.locator('#msstBadge').filter({hasText:'已连接'}).waitFor();assert.equal(await page.locator('#msstEmbeddedFrame').getAttribute('data-reused'),'yes');await page.locator('#msstCloseEmbed').click();await page.locator('#msstCheck').click();await page.locator('#msstCheck').isEnabled();assert.equal(await page.locator('#msstEmbeddedFrame').count(),0);
  await page.locator('#msstSettings').click();await page.locator('#msstUrl').fill('http://external.example');await page.locator('#msstSettingsForm button[type=submit]').click();await page.locator('#msstSettingsError').filter({hasText:'本机 HTTP'}).waitFor();await page.locator('#msstUrl').fill('http://127.0.0.1:7860');await page.locator('#msstLauncher').fill('');await page.locator('#msstSettingsForm button[type=submit]').click();await page.locator('#msstSettingsDialog').waitFor({state:'hidden'});
  await page.setViewportSize({width:390,height:844});assert.ok(!await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2));await page.locator('[data-tab="workflow"]').click();await page.locator('#productionManage').click();assert.ok(!await page.locator('#productionAssetDialog').evaluate(e=>e.scrollWidth>e.clientWidth+2));await page.locator('#productionAssetClose').click();assert.ok(!await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2));
  assert.deepEqual(await fs.readFile(source),original);assert.deepEqual(errors,[]);assert.equal(liveRequests,0);
  console.log('PASS: four-stage production home, opt-in legacy tools, no SV polling, quoted asset registration, video mix handoff, native open intent, DAW prefill, MSST launch/embed/settings and mobile layout');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
