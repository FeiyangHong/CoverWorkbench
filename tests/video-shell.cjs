/* Shared-shell integration with synthetic projects and no private media. */
const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{
 const base=process.argv[2],browser=await chromium.launch({headless:true,...(process.env.CW_BROWSER_CHANNEL?{channel:process.env.CW_BROWSER_CHANNEL}:{})});
 try{
  const context=await browser.newContext({viewport:{width:1500,height:1000}}),page=await context.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  async function fixture(name){const created=await (await context.request.post(base+'/api/video-create/new',{data:{name}})).json();const doc=(await (await context.request.get(base+'/api/video-project/'+created.id)).json()).project;doc.cues=[{id:'A',start:1,end:3,original:'Original caption',translation:'Translation'}];return (await (await context.request.post(base+'/api/video-save/'+created.id,{data:doc})).json()).id;}
  const a=await fixture('Shell Video A'),b=await fixture('Shell Video B');
  // Video creation must work even when the music workbench has no imported SVP.
  await page.route('**/api/projects',route=>route.fulfill({json:[]}));await page.goto(base);await page.locator('#emptyWelcome').waitFor();
  assert.equal(await page.locator('iframe').count(),0,'Video should load only on demand');assert.ok(await page.locator('[data-tab="video"]').isEnabled());
  await page.locator('[data-tab="video"]').click();const child=page.frameLocator('#videoWorkspaceFrame');
  await page.waitForFunction(()=>!document.querySelector('#videoNewProject').disabled);
  await child.locator('#projects').selectOption(a);await child.locator('#name').filter({hasText:'Shell Video A'}).waitFor();
  await page.waitForFunction(id=>new URL(location.href).searchParams.get('videoProject')===id,a);
  assert.equal(new URL(page.url()).pathname,'/');assert.equal(await child.locator('#cwExitButton').count(),0);assert.equal(await page.locator('#cwExitButton').count(),1);assert.ok(!await child.locator('body>header').isVisible());assert.ok(!await page.locator('.project-heading').isVisible());
  await page.locator('#videoProjects [data-video-project="'+a+'"]').waitFor();
  const frame=page.frames().find(f=>f.url().includes('embed=1'));
  const beforeFocus=await child.locator('#dirty').innerText(),normalHeight=(await page.locator('#videoWorkspaceFrame').boundingBox()).height;await page.locator('#videoFocusToggle').click();assert.ok(!await page.locator('.tabs').isVisible());assert.ok((await page.locator('#videoWorkspaceFrame').boundingBox()).height>normalHeight+20);assert.equal(await child.locator('#dirty').innerText(),beforeFocus);await page.locator('#videoFocusToggle').click();assert.ok(await page.locator('.tabs').isVisible());
  await child.locator('[data-cue="A:original"]').fill('Draft caption');await child.locator('#captionZoom').selectOption('4');
  await frame.evaluate(()=>{const p=window.CWVideoStudio.player;p.currentTime=2;window.pauseCalls=0;const pause=p.pause.bind(p);p.pause=()=>{window.pauseCalls++;pause();};});
  const environmentRefresh=page.waitForRequest(r=>r.url().endsWith('/api/video-status'));await page.evaluate(()=>window.dispatchEvent(new Event('cw-environment-changed')));await environmentRefresh;
  const history=await frame.evaluate(()=>window.CWVideoStudio.history.status().undo);
  await page.locator('[data-tab="mix-guide"]').click();assert.ok(!await page.locator('#videoWorkspaceFrame').isVisible());assert.equal(await frame.evaluate(()=>window.CWVideoStudio.get().visible),false);assert.ok(await frame.evaluate(()=>window.pauseCalls>0));
  await page.locator('#mgDemoPlay').click();await page.waitForFunction(()=>document.querySelector('#mgDemoPlay').textContent.includes('暂停'));
  await page.locator('[data-tab="video"]').click();assert.ok(!(await page.locator('#mgDemoPlay').innerText()).includes('暂停'));assert.equal(await child.locator('[data-cue="A:original"]').inputValue(),'Draft caption');assert.equal(await child.locator('#captionZoom').inputValue(),'4');assert.equal(await frame.evaluate(()=>window.CWVideoStudio.get().position),2);assert.equal(await frame.evaluate(()=>window.CWVideoStudio.history.status().undo),history);
  await child.locator('[data-cue="A:original"]').press('Control+z');assert.equal(await child.locator('[data-cue="A:original"]').inputValue(),'Original caption');await child.locator('[data-cue="A:original"]').press('Control+y');
  assert.equal(await page.evaluate(()=>{const e=new Event('beforeunload',{cancelable:true});window.dispatchEvent(e);return e.defaultPrevented;}),true,'Parent refresh must guard hidden child drafts');
  await page.locator('#environmentSettings').focus();await page.keyboard.press('Control+s');await child.locator('#dirty').filter({hasText:'已保存'}).waitFor();
  const saved=(await (await context.request.get(base+'/api/video-project/'+a)).json()).project;assert.equal(saved.cues[0].original,'Draft caption');
  await child.locator('[data-cue="A:original"]').fill('Saved when changing video');await page.locator('#videoProjects [data-video-project="'+b+'"]').click();await child.locator('#name').filter({hasText:'Shell Video B'}).waitFor();
  await page.waitForFunction(id=>new URL(location.href).searchParams.get('videoProject')===id,b);assert.equal((await (await context.request.get(base+'/api/video-project/'+a)).json()).project.cues[0].original,'Saved when changing video');
  await page.goBack();await child.locator('#name').filter({hasText:'Shell Video A'}).waitFor();await page.goForward();await child.locator('#name').filter({hasText:'Shell Video B'}).waitFor();
  const legacy=await context.newPage();legacy.on('pageerror',e=>errors.push(e.message));await legacy.goto(base+'/video/index.html?project='+encodeURIComponent(a));await legacy.waitForURL(url=>url.pathname==='/'&&url.searchParams.get('tab')==='video');await legacy.frameLocator('#videoWorkspaceFrame').locator('#name').filter({hasText:'Shell Video A'}).waitFor();await legacy.close();
  const encoded=await context.newPage();await encoded.goto(base+'/?tab=video&videoProject='+encodeURIComponent(a));await encoded.frameLocator('#videoWorkspaceFrame').locator('#name').filter({hasText:'Shell Video A'}).waitFor();const entries=await encoded.evaluate(()=>history.length);await encoded.locator('[data-tab="mix-guide"]').click();await encoded.goBack();await encoded.locator('#videoWorkspaceFrame').waitFor({state:'visible'});assert.equal(await encoded.evaluate(()=>history.length),entries+1);await encoded.close();
  const bookmark=await context.newPage();await bookmark.goto(base+'/?tab=mix-guide');await bookmark.locator('#mix-guide').waitFor({state:'visible'});assert.equal(await bookmark.locator('iframe').count(),0);await bookmark.close();
  if(process.env.CW_SHELL_SCREENSHOTS)await page.screenshot({path:process.env.CW_SHELL_SCREENSHOTS+'-desktop.png'});
  await page.setViewportSize({width:390,height:844});await child.locator('#name').waitFor();
  await page.waitForFunction(()=>{const b=document.querySelector('.tabs [data-tab=video]').getBoundingClientRect(),n=document.querySelector('.tabs').getBoundingClientRect();return b.left>=n.left-1&&b.right<=n.right+1;});
  assert.ok(!await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2));assert.ok(!await frame.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2));assert.ok((await page.locator('#videoWorkspaceFrame').boundingBox()).height>300);
  if(process.env.CW_SHELL_SCREENSHOTS)await page.screenshot({path:process.env.CW_SHELL_SCREENSHOTS+'-mobile.png'});
  await frame.evaluate(()=>{window.exitSeen=0;window.addEventListener('cw-workbench-exit',()=>window.exitSeen++);});await page.evaluate(()=>window.dispatchEvent(new Event('cw-workbench-exit')));assert.equal(await frame.evaluate(()=>window.exitSeen),1);
  assert.deepEqual(errors,[]);console.log('PASS: lazy video work area in empty music install, shared navigation/project library, draft/history/position retention, audio suspension, save/exit forwarding, back/forward, legacy links and mobile fit');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
