/* Undo real UI edits against an isolated synthetic server and saved documents. */
const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.CW_BROWSER_CHANNEL?{channel:process.env.CW_BROWSER_CHANNEL}:{})});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1100}}),page=await context.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(process.argv[2]+'/video/index.html?standalone=1');await page.locator('#new').click();await page.locator('#newName').fill('Subtitle Undo');await page.locator('#promptForm button[type=submit]').click();await page.locator('body.has-document').waitFor();await page.locator('#workflowDetails').evaluate(el=>el.open=true);await page.locator('[data-step="mv"]').waitFor();
  await page.evaluate(()=>{const ui=window.CWVideoStudio;ui.get().doc.cues=[{id:'A',start:1,end:3,original:'Original',translation:'Translation'},{id:'B',start:4,end:6,original:'Second',translation:'Second translation'}];ui.renderRows();ui.mark();});
  async function save(){await page.locator('#save').click();await page.waitForFunction(()=>!document.querySelector('#save').disabled&&document.querySelector('#dirty').textContent==='已保存');}
  async function reload(){await page.reload();await page.locator('body.has-document').waitFor();await page.locator('#workflowDetails').evaluate(el=>el.open=true);await page.locator('[data-step="mv"]').waitFor();}
  const status=()=>page.evaluate(()=>window.CWVideoStudio.history.status());
  const content=()=>page.evaluate(()=>structuredClone(window.CWVideoStudio.get().doc.cues));
  const text=()=>page.locator('[data-cue="A:original"]');
  const undo=()=>page.keyboard.press('Control+z'),redo=()=>page.keyboard.press('Control+y');
  await save();await reload();const initial=await content();
  assert.equal(await page.locator('[data-history="undo"]').isEnabled(),false);
  assert.equal(await page.locator('[data-history="redo"]').isEnabled(),false);
  await page.locator('#out').fill('20');await page.locator('#captionZoom').selectOption('4');await page.locator('#captionSnap').uncheck();await page.locator('#captionScroll').scrollIntoViewIfNeeded();
  const edge=page.locator('.lane-translation [data-caption="A"] [data-edge="end"]'),box=await edge.boundingBox();
  await page.mouse.move(box.x+box.width/2,box.y+15);await page.mouse.down();await page.mouse.move(box.x+80,box.y+15,{steps:20});await page.mouse.up();
  const dragged=await content();assert.notDeepEqual(dragged,initial);assert.equal((await status()).undo,1);assert.equal(dragged[0].end,3);
  const position=await page.locator('#seek').inputValue(),zoom=await page.locator('#captionZoom').inputValue();
  await undo();assert.deepEqual(await content(),initial);assert.equal(await page.locator('#dirty').innerText(),'已保存');assert.equal(await page.locator('#seek').inputValue(),position);assert.equal(await page.locator('#captionZoom').inputValue(),zoom);
  await redo();assert.deepEqual(await content(),dragged);await undo();
  // Whole typing sessions, including edits inside the focused table, use project history.
  await text().fill('Changed');await text().pressSequentially(' text');assert.equal((await status()).undo,1);
  await text().press('Control+z');assert.equal(await text().inputValue(),'Original');
  await text().press('Control+Shift+z');assert.equal(await text().inputValue(),'Changed text');
  await page.locator('#captionScroll').scrollIntoViewIfNeeded();await page.locator('.lane-original [data-caption="A"]').focus();await page.keyboard.press('F2');
  await page.locator('#captionTextInput').fill('Inline');await page.locator('#captionTextInput').pressSequentially(' edit');
  await page.locator('#captionTextInput').press('Control+z');await page.locator('#captionTextEditor').waitFor({state:'hidden'});assert.equal(await text().inputValue(),'Changed text');
  await redo();assert.equal(await text().inputValue(),'Inline edit');await undo();
  const beforeCancel=await status();await page.locator('.lane-original [data-caption="A"]').focus();await page.keyboard.press('F2');await page.locator('#captionTextInput').fill('Discard');await page.locator('#captionTextInput').press('Escape');
  assert.deepEqual(await status(),beforeCancel);await redo();assert.equal(await text().inputValue(),'Inline edit');
  // Save preserves undo/redo, and returning to a saved state updates the dirty indicator.
  await save();const savedRevision=await page.locator('#revision').innerText();await page.locator('[data-history="undo"]').click();assert.equal(await text().inputValue(),'Changed text');assert.equal(await page.locator('#dirty').innerText(),'有未保存修改');assert.equal(await page.locator('#revision').innerText(),savedRevision);
  const stored=await page.evaluate(()=>window.CWVideoStudio.api('/api/video-project/'+window.CWVideoStudio.get().doc.id));assert.equal(stored.project.cues[0].original,'Inline edit');
  await page.locator('[data-history="redo"]').click();assert.equal(await page.locator('#dirty').innerText(),'已保存');
  await page.locator('[data-panel="layout"]').click();const size=page.locator('[data-style="global:original:size"]'),oldSize=await size.inputValue();await size.fill('55');await size.press('Control+z');assert.equal(await size.inputValue(),oldSize);await size.press('Control+y');assert.equal(await size.inputValue(),'55');
  const beforeDelete=await content();await page.locator('[data-delete="A"]').click();assert.equal((await content()).length,1);await undo();assert.deepEqual(await content(),beforeDelete);
  await text().fill('A new branch');assert.equal((await status()).redo,0);
  const count=(await status()).undo;await page.locator('#search').fill('search');await page.locator('#search').press('Control+z');assert.equal((await status()).undo,count);await page.locator('#search').fill('');
  await save();await reload();assert.equal((await status()).undo,0);assert.equal((await status()).redo,0);
  // Real server reconciliation: a saved audio-clock offset rebases the entire history once.
  await page.evaluate(async()=>{const ui=window.CWVideoStudio,health=await ui.api('/api/health');await ui.api('/api/video-captions/'+ui.get().doc.id,{original:health.root+'/input.lrc',clock:'audio'});});
  await page.locator('#reload').click();await page.waitForFunction(()=>window.CWVideoStudio.get().doc.timing?.clock==='audio');
  const id=await page.evaluate(()=>window.CWVideoStudio.get().doc.cues[0].id),original=page.locator('[data-cue="'+id+':original"]');
  await page.evaluate(()=>{const ui=window.CWVideoStudio;ui.get().doc.cues[0].translationTiming={start:1.123456,end:3.234567};ui.mark();});
  await page.locator('[data-panel=sound]').click();await page.locator('#audioOffset').fill('2');await original.fill('Offset edit');await save();assert.equal((await content())[0].start,3);
  await page.locator('[data-history="undo"]').click();assert.equal(await original.inputValue(),'First line');assert.equal((await content())[0].start,3);await save();
  const reconciled=await page.evaluate(()=>window.CWVideoStudio.api('/api/video-project/'+window.CWVideoStudio.get().doc.id));assert.equal(reconciled.project.cues[0].start,3);assert.equal(reconciled.project.timing.appliedAudioOffset,2);assert.equal(reconciled.project.cues[0].translationTiming.start,3.123456);
  await page.locator('[data-history="redo"]').click();assert.equal(await original.inputValue(),'Offset edit');assert.equal((await content())[0].start,3);
  await page.setViewportSize({width:390,height:844});await page.locator('#captionScroll').scrollIntoViewIfNeeded();assert.ok(!await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2));
  if(errors.length)throw Error(errors.join('\n'));
  console.log('PASS: one-step drag/text undo, Ctrl+Z/Y/Shift+Z, cancel/redo, save checkpoints, styles/deletion/branching, native search editing, offset rebasing and mobile controls');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
