/* Real source handoff in a disposable relocated install; never run on user projects. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path');
(async()=>{
 const base=process.argv[2],browser=await chromium.launch({headless:true,...(process.env.CW_BROWSER_CHANNEL?{channel:process.env.CW_BROWSER_CHANNEL}:{})});
 try{
  const context=await browser.newContext({viewport:{width:1500,height:1000}}),page=await context.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  async function api(url,data){const response=await context.request[data===undefined?'get':'post'](base+url,data===undefined?{}:{data});const result=await response.json();assert.ok(response.ok(),JSON.stringify(result));return result;}
  const root=(await api('/api/health')).root,allowed=path.resolve(__dirname,'../work')+path.sep;
  assert.ok(path.resolve(root).startsWith(allowed)&&path.basename(root).startsWith('portable checkout '),'Only disposable portable fixtures may be changed');
  const music=(await api('/api/projects'))[0],bundlePath=path.join(root,'data/projects',music.id+'.json'),bundle=JSON.parse(await fs.readFile(bundlePath,'utf8'));
  const mix=path.join(root,'final mix.wav'),wave=Buffer.alloc(2044);wave.write('RIFF',0);wave.writeUInt32LE(2036,4);wave.write('WAVEfmt ',8);wave.writeUInt32LE(16,16);wave.writeUInt16LE(1,20);wave.writeUInt16LE(1,22);wave.writeUInt32LE(48000,24);wave.writeUInt32LE(96000,28);wave.writeUInt16LE(2,32);wave.writeUInt16LE(16,34);wave.write('data',36);wave.writeUInt32LE(2000,40);await fs.writeFile(mix,wave);
  bundle.project.audio.mix={original:mix,preview:mix,format:{sample_rate:48000,bits_per_raw_sample:16,channels:1}};await fs.writeFile(bundlePath,JSON.stringify(bundle));
  await api('/api/state/'+music.id,{subtitles:[{start:1,end:3,original:'Music original',translation:'音乐译文'}]});
  await page.goto(base);await page.locator('#musicVideoSummary').filter({hasText:'1 组含译文'}).waitFor();
  await page.locator('#musicVideoOpen').click();await page.locator('#mvSources').filter({hasText:'final mix.wav'}).waitFor();await page.waitForFunction(()=>!document.querySelector('#mvSubmit').disabled);
  assert.equal(await page.locator('#mvName').inputValue(),'My First Cover Video');assert.ok((await page.locator('#mvSources').innerText()).includes('音乐工程已保存字幕'));
  await page.locator('#mvName').fill('Linked Music Video');await page.locator('#mvSubmit').click();
  const child=page.frameLocator('#videoWorkspaceFrame');await child.locator('#name').filter({hasText:'Linked Music Video'}).waitFor();await page.locator('#videoMusicBar').filter({hasText:'My First Cover'}).waitFor();
  let link=await api('/api/music-video/'+music.id),doc=(await api('/api/video-project/'+link.linkedId)).project;
  assert.equal(doc.audio,mix);assert.equal(doc.cues[0].translation,'音乐译文');assert.equal(doc.cues[0].start,1);
  const id=doc.id;
  await child.locator('[data-cue="L0001:original"]').fill('Video-side edit');await child.locator('[data-panel=sound]').click();await child.locator('#subtitleShift').fill('.25');
  await page.locator('#mvReturnMusic').click();await page.locator('#musicVideoOpen').click();
  assert.equal(await child.locator('[data-cue="L0001:original"]').inputValue(),'Video-side edit','Reentry replaced a video draft');
  await page.locator('#mvManageFromVideo').click();await page.waitForFunction(()=>!document.querySelector('#mvSubmit').disabled);
  doc=(await api('/api/video-project/'+id)).project;assert.equal(doc.cues[0].original,'Video-side edit','Pending draft was not saved before material refresh');
  assert.ok(!await page.locator('#mvUpdateAudio').isChecked());assert.ok(!await page.locator('#mvUpdateCaptions').isChecked());
  await page.locator('#mvClose').click();
  // A source change is an explicit update opportunity, never an implicit re-import.
  await api('/api/state/'+music.id,{subtitles:[{start:2,end:4,original:'New music text',translation:'新译文'}]});
  await page.locator('#mvReturnMusic').click();await page.locator('#musicVideoOpen').click();assert.equal(await child.locator('[data-cue="L0001:original"]').inputValue(),'Video-side edit');
  await page.locator('#mvManageFromVideo').click();await page.waitForFunction(()=>!document.querySelector('#mvSubmit').disabled);
  await page.locator('#mvUpdateCaptions').check();await page.locator('#mvSubmit').click();await child.locator('[data-cue="L0001:original"]').filter({visible:true}).waitFor();
  await page.waitForFunction(()=>document.querySelector('#videoWorkspaceFrame').contentWindow.CWVideoStudio.get().doc.cues[0].original==='New music text');
  doc=(await api('/api/video-project/'+id)).project;assert.equal(doc.cues[0].start,2);assert.equal(doc.subtitleShift,0);
  // Explicitly bind an existing edited project without changing its revision or bytes.
  const existing=await api('/api/video-create/new',{name:'Existing Link Video'});let existingDoc=(await api('/api/video-project/'+existing.id)).project;
  existingDoc.cues=[{id:'Kept',start:8,end:10,original:'Already edited',translation:'保留',translationTiming:{start:8.5,end:10.5}}];existingDoc.styles.original.size=51;existingDoc.audioOffset=4;
  await api('/api/video-save/'+existing.id,existingDoc);const videoPath=path.join(root,'projects/video',existing.id,'project.json'),before=await fs.readFile(videoPath,'utf8');
  await page.locator('#mvManageFromVideo').click();await page.waitForFunction(()=>!document.querySelector('#mvSubmit').disabled);await page.locator('#mvMode').selectOption('bind');await page.locator('#mvExisting').selectOption(existing.id);await page.locator('#mvSubmit').click();
  await child.locator('#name').filter({hasText:existing.id}).waitFor();assert.equal(await fs.readFile(videoPath,'utf8'),before);assert.equal(await child.locator('[data-cue="Kept:original"]').inputValue(),'Already edited');
  await page.locator('#mvManageFromVideo').click();await page.waitForFunction(()=>!document.querySelector('#mvSubmit').disabled);assert.ok(await page.locator('#mvUpdateCaptions').isDisabled());await page.locator('#mvUpdateAudio').check();assert.ok(await page.locator('#mvUpdateCaptions').isEnabled());
  await page.locator('#mvUnlink').click();await page.locator('#mvLinkCurrent').waitFor();assert.equal(await fs.readFile(videoPath,'utf8'),before);
  await page.locator('#mvMusicChoice').selectOption(music.id);await page.locator('#mvLinkCurrent').click();await page.waitForFunction(()=>!document.querySelector('#mvSubmit').disabled);assert.equal(await page.locator('#mvMode').inputValue(),'bind');assert.equal(await page.locator('#mvExisting').inputValue(),existing.id);await page.locator('#mvSubmit').click();await page.locator('#mvManageFromVideo').waitFor();assert.equal(await fs.readFile(videoPath,'utf8'),before);
  // Song selection exits the video workspace; the dedicated video entry returns to its own project.
  await page.locator('[data-workspace="music"]').click();await page.locator('#projects [data-project="'+music.id+'"]').click();await page.waitForFunction(()=>!document.querySelector('#musicVideoOpen').disabled);await page.locator('#musicVideoOpen').waitFor({state:'visible'});
  await page.locator('#productionAdvanced').evaluate(e=>e.open=true);await page.locator('#legacyToolsEnabled').check();await page.locator('[data-tab="lyrics"]').click();await page.locator('[data-cue="0"] [data-field="translation"]').fill('Unsaved music translation');
  await page.locator('#musicVideoManage').click();await page.waitForFunction(()=>!document.querySelector('#mvSubmit').disabled);await page.locator('#mvDraftNotice').waitFor({state:'visible'});
  const sourceBefore=await api('/api/music-video/'+music.id);await page.locator('#mvSaveDraft').click();await page.locator('#mvDraftNotice').waitFor({state:'hidden'});assert.notEqual((await api('/api/music-video/'+music.id)).signature,sourceBefore.signature);
  await page.locator('#mvAudioPath').fill('"'+mix+'"');assert.ok(await page.locator('#mvSubmit').isDisabled());await page.locator('#mvPreview').click();await page.waitForFunction(()=>!document.querySelector('#mvSubmit').disabled);await page.locator('#mvClose').click();
  await page.locator('[data-tab="video"]').click();await child.locator('#name').filter({hasText:existing.id}).waitFor();assert.ok(!await page.locator('#musicVideoDialog').isVisible());
  await page.setViewportSize({width:390,height:844});await page.waitForFunction(()=>document.querySelector('#videoWorkspaceFrame').getBoundingClientRect().height>300);assert.ok(!await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2));
  await page.locator('#mvManageFromVideo').click();await page.waitForFunction(()=>!document.querySelector('#mvSubmit').disabled);assert.ok(!await page.locator('#musicVideoDialog').evaluate(e=>e.scrollWidth>e.clientWidth+2));await page.locator('#mvClose').click();
  assert.deepEqual(errors,[]);console.log('PASS: music-to-video creation with real sources, reverse links, draft-safe reentry, explicit updates, unchanged binding/unlink, saved-subtitle handoff, quoted paths and mobile layout');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
