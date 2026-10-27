/* Only a disposable installation is permitted; no native apps or real song imports. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),path=require('node:path');
(async()=>{
 const base=process.argv[2],browser=await chromium.launch({headless:true,...(process.env.CW_BROWSER_CHANNEL?{channel:process.env.CW_BROWSER_CHANNEL}:{})});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  async function api(url,body){const r=await context.request[body===undefined?'get':'post'](base+url,body===undefined?{}:{data:body});const d=await r.json();assert.ok(r.ok(),JSON.stringify(d));return d;}
  const root=(await api('/api/health')).root;
  assert.ok(path.resolve(root).startsWith(path.resolve(__dirname,'../work')+path.sep)&&path.basename(root).startsWith('portable checkout '));
  const title='合成歌曲 テスト #1 100%',directory='合成歌手 - テスト 曲';
  await page.goto(base);await page.locator('#importProject').click();await page.locator('#importStartMode').selectOption('svp');
  await page.locator('#importProjectForm [name=svp]').fill(path.join(root,'input.svp'));
  await page.locator('#importProjectForm [name=folderName]').fill(directory);
  await page.locator('#importProjectForm [name=title]').fill(title);await page.locator('#importProjectForm [name=artist]').fill('合成歌手');
  await page.locator('#importProjectForm button[type=submit]').click();await page.locator('#importProjectDialog').waitFor({state:'hidden'});await page.locator('#title').filter({hasText:title}).waitFor();
  const music=(await api('/api/projects')).find(p=>p.title===title);assert.equal(path.basename(music.pilot),directory);
  await page.locator('#productionBuildSong').click();assert.equal(await page.locator('#dawName').inputValue(),title);
  const videoName='合成视频 テスト #1 100%';
  await page.goto(base+'/video/index.html?standalone=1');await page.locator('#new').click();await page.locator('#newName').fill(videoName);await page.locator('#promptForm button[type=submit]').click();await page.locator('#name').filter({hasText:videoName}).waitFor();
  await page.locator('#add').click();await page.locator('[data-cue$=":original"]').fill('合成 テスト字幕');await page.locator('#save').click();await page.locator('#dirty').filter({hasText:'已保存'}).waitFor();
  let saved=(await api('/api/video-project/'+encodeURIComponent(videoName))).project;assert.equal(saved.cues[0].original,'合成 テスト字幕');
  await page.reload();await page.locator('#name').filter({hasText:videoName}).waitFor();assert.equal(new URL(page.url()).searchParams.get('project'),videoName);
  const invalid=await context.request.post(base+'/api/video-create/new',{data:{name:'bad:name'}});assert.equal(invalid.status(),400);assert.match((await invalid.json()).error,/Windows/);
  saved=(await api('/api/video-project/'+encodeURIComponent(videoName))).project;assert.equal(saved.revision,2);
  assert.deepEqual(errors,[]);
  console.log('PASS: Unicode music import/folder/DAW prefill and video create/save/reload with encoded #/% names; illegal Windows names rejected');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
