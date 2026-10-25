/* Synthetic timeline interactions; never opens or edits a user's creative project. */
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.CW_BROWSER_CHANNEL?{channel:process.env.CW_BROWSER_CHANNEL}:{})});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1100}}),page=await context.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(process.argv[2]+'/video/index.html?standalone=1');
  await page.locator('#new').click();await page.locator('#newName').fill('Timeline Interactions');await page.locator('#promptForm button[type=submit]').click();
  await page.locator('#name').filter({hasText:'Timeline Interactions'}).waitFor();
  await page.locator('body.has-document').waitFor();await page.locator('#workflowDetails').evaluate(el=>el.open=true);await page.locator('[data-step="mv"]').waitFor();
  const lane=key=>page.locator(`.lane-${key} [data-caption="A"]`);
  const ranges=()=>page.evaluate(()=>{const r=window.CWVideoStudio.get().doc.cues[0],t=window.CWCaptionTiming;return {original:t.get(r,'original'),translation:t.get(r,'translation')};});
  async function reset(independent=false){
   await page.evaluate(independent=>{
    const ui=window.CWVideoStudio;ui.get().doc.cues=[
     {id:'A',start:1,end:3,original:'Original A',translation:'Translation A',...(independent?{translationTiming:{start:1.5,end:3.5}}:{})},
     {id:'B',start:4,end:6,original:'Original B',translation:'Translation B'},
     {id:'C',start:12,end:14,original:'Original C',translation:'Translation C'}];
    ui.renderRows();ui.mark();const out=document.querySelector('#out');out.value=20;out.dispatchEvent(new Event('input'));
   },independent);
   await page.locator('#captionLink').uncheck();await page.locator('#captionSnap').check();
   await page.locator('#captionZoom').selectOption('4');
   // The viewport survives ResizeObserver redraws; individual caption blocks do not.
   await page.locator('#captionScroll').scrollIntoViewIfNeeded();await page.locator('#captionScroll').evaluate(el=>el.scrollLeft=0);
  }
  async function resizeEnd(target,alt=false){
   const edge=lane('original').locator('[data-edge="end"]'),box=await edge.boundingBox();
   const scale=await page.locator('#captionCanvas').evaluate(el=>el.getBoundingClientRect().width/20);
   await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down();
   if(alt)await page.keyboard.down('Alt');
   await page.mouse.move(box.x+box.width/2+(target-3)*scale,box.y+box.height/2,{steps:8});
   const snap=await page.locator('#captionSnapGuide').isVisible();await page.mouse.up();if(alt)await page.keyboard.up('Alt');return snap;
  }
  await reset();
  if(!await resizeEnd(3.98))throw Error('Nearby subtitle boundary did not show a snap guide');
  let r=await ranges();if(r.original.end!==4||r.translation.end!==3)throw Error('Snapped resize changed the other language or missed its target');
  await reset();if(await resizeEnd(3.98,true))throw Error('Alt did not bypass snapping');
  r=await ranges();if(Math.abs(r.original.end-3.98)>.006||r.translation.end!==3)throw Error('Alt resize lost independent precision');
  await reset();await page.locator('#captionSnap').uncheck();if(await resizeEnd(3.98))throw Error('Disabled snap still active');
  await reset();await lane('original').focus();await page.keyboard.press('ArrowRight');await page.keyboard.press('ArrowRight');
  if((await ranges()).original.start!==1.1)throw Error('Repeated keyboard adjustment lost timeline focus');
  await reset(true);await page.locator('#captionLink').check();
  await lane('translation').focus();await page.keyboard.press('ArrowRight');
  r=await ranges();if(r.original.start!==1.05||r.translation.start!==1.55||r.original.end!==3.05||r.translation.end!==3.55)throw Error('Linked edit lost an existing language offset');
  await page.locator('#captionLink').uncheck();await lane('translation').focus();await page.keyboard.press('Shift+ArrowRight');
  r=await ranges();if(r.original.start!==1.05||r.translation.start!==2.05)throw Error('Translation-only keyboard adjustment changed original');
  // A real browser double-click opens the editor; live edits affect just one language.
  await lane('translation').dblclick({position:{x:25,y:16}});
  await page.locator('#captionTextInput').fill('Changed in timeline');
  if(await page.locator('[data-cue="A:translation"]').inputValue()!=='Changed in timeline'||await page.locator('[data-cue="A:original"]').inputValue()!=='Original A')throw Error('Timeline text edit was not language-specific');
  await page.locator('#captionTextInput').press('Control+Enter');await page.locator('#captionTextEditor').waitFor({state:'hidden'});
  await lane('translation').hover();await lane('translation').locator('[data-edit]').click();
  await page.locator('#captionTextInput').fill('Cancelled change');await page.locator('#captionTextInput').press('Escape');
  if(await page.locator('[data-cue="A:translation"]').inputValue()!=='Changed in timeline')throw Error('Esc did not restore the previous text');
  if(process.env.CW_TIMELINE_SCREENSHOTS)await page.screenshot({path:process.env.CW_TIMELINE_SCREENSHOTS+'-desktop.png',fullPage:true});
  await page.locator('#save').click();await page.locator('#dirty').filter({hasText:'已保存'}).waitFor();await page.reload();
  await page.locator('[data-cue="A:translation"]').filter({visible:true}).waitFor();
  r=await ranges();if(r.original.start!==1.05||r.translation.start!==2.05||await page.locator('[data-cue="A:translation"]').inputValue()!=='Changed in timeline')throw Error('Independent timing or timeline text did not survive save/reload');
  const layers=await page.evaluate(()=>{
   const ui=window.CWVideoStudio,p=ui.player,renderer=window.CWCaptionPreview,old={paint:renderer.paint,prefetch:renderer.prefetch,clear:renderer.clear};let now=1.5,current=null,next=null;
   Object.defineProperty(p,'currentTime',{configurable:true,get:()=>now});
   renderer.paint=(_,payload)=>{current=payload.cues;return true;};renderer.prefetch=payload=>{next=payload.cues;};renderer.clear=()=>{current=[];};
   const result=[];try{for(const t of [1.5,2.5,3.5]){now=t;p.dispatchEvent(new Event('timeupdate'));result.push({current,next});}}finally{Object.assign(renderer,old);delete p.currentTime;}return result;
  });
  if(layers[0].current[0].translation||!layers[0].current[0].original||!layers[1].current[0].translation||layers[2].current[0].original||!layers[2].current[0].translation||layers[1].next[0].original)throw Error('Live caption layers or boundary prefetch ignored independent language clocks');
  // Feed deterministic playback clock events without a media decoder in a clean install.
  await page.locator('#out').fill('200');await page.locator('#captionZoom').selectOption('4');
  await page.locator('#captionAutoFollow').uncheck();
  await page.evaluate(()=>{
   const p=window.CWVideoStudio.player;window.testClock=150;
   Object.defineProperty(p,'currentTime',{configurable:true,get:()=>window.testClock});
   Object.defineProperty(p,'paused',{configurable:true,get:()=>false});
   document.querySelector('#captionScroll').scrollLeft=0;p.dispatchEvent(new Event('timeupdate'));
  });
  if(await page.locator('#captionScroll').evaluate(el=>el.scrollLeft)!==0)throw Error('Disabled follow moved the viewport');
  await page.locator('#captionAutoFollow').check();
  if(!await page.locator('#captionScroll').evaluate(el=>el.scrollLeft>0))throw Error('Enabling follow did not find the playhead');
  await page.evaluate(()=>{window.testClock=195;window.CWVideoStudio.player.dispatchEvent(new Event('timeupdate'));});
  const right=await page.locator('#captionScroll').evaluate(el=>el.scrollLeft);
  await page.evaluate(()=>{window.testClock=50;window.CWVideoStudio.player.dispatchEvent(new Event('timeupdate'));});
  if(await page.locator('#captionScroll').evaluate(el=>el.scrollLeft)>=right)throw Error('Playback/loop return did not follow backwards');
  await page.locator('#captionAutoFollow').uncheck();await page.locator('#captionSnap').uncheck();await page.locator('#captionLink').check();
  await page.evaluate(()=>{const p=window.CWVideoStudio.player;delete p.currentTime;delete p.paused;});
  const other=await context.newPage();await other.goto(page.url());await other.waitForFunction(()=>window.CWVideoStudio?.get().doc&&document.querySelector('#captionLink')?.checked&&!document.querySelector('#captionAutoFollow').checked&&!document.querySelector('#captionSnap').checked);
  if(await other.locator('#captionAutoFollow').isChecked()||await other.locator('#captionSnap').isChecked()||!await other.locator('#captionLink').isChecked())throw Error('Timeline preferences were not restored');await other.close();
  await page.setViewportSize({width:390,height:844});await page.locator('#captionScroll').scrollIntoViewIfNeeded();await lane('original').focus();await page.keyboard.press('F2');await page.locator('#captionTextInput').waitFor();
  if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2))throw Error('Timeline/editor overflows mobile viewport');
  if(process.env.CW_TIMELINE_SCREENSHOTS)await page.screenshot({path:process.env.CW_TIMELINE_SCREENSHOTS+'-mobile.png',fullPage:true});
  await page.locator('#captionTextCancel').click();
  if(errors.length)throw Error(errors.join('\n'));
  console.log('PASS: timeline playback-follow toggle, boundary snap and Alt bypass, independent/linked clocks, inline double-click editing, cancellation, persistence and mobile layout');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
