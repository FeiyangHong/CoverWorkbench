/* Shelf sorting, real lyric downloads and default named-project storage, in an empty checkout. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs/promises');
(async()=>{
 const base=process.argv[2],browser=await chromium.launch({headless:true,...(process.env.CW_BROWSER_CHANNEL?{channel:process.env.CW_BROWSER_CHANNEL}:{})});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  async function api(route,body){const r=await page.request[body===undefined?'get':'post'](base+route,body===undefined?{}:{data:body}),d=await r.json();assert.ok(r.ok(),JSON.stringify(d));return d;}
  const root=(await api('/api/health')).root;assert.ok(path.resolve(root).startsWith(path.resolve(__dirname,'../work')+path.sep)&&path.basename(root).startsWith('portable checkout '));
  const created=[];
  for(const [i,title] of ['Shelf Alpha','Shelf Beta','Shelf Gamma'].entries()){
   const p=await api('/api/project-import/new',{svp:path.join(root,'input.svp'),title,artist:'Fixture',language:'en'});created.push(p);
   const filename=path.join(root,'data/projects',p.id+'.json'),d=JSON.parse(await fs.readFile(filename,'utf8'));d.project.builtAt=`2099-01-0${i+1} 00:00:00`;await fs.writeFile(filename,JSON.stringify(d));
   for(const f of [filename,path.join(p.pilot,'analysis/review.json'),p.working])await fs.utimes(f,1578000000+i*100,1578000000+i*100);
  }
  await page.goto(base);await page.locator('#projects [data-project]').first().waitFor();
  const select=page.locator('[data-shelf=music] select');await select.selectOption('created-asc');
  await page.waitForFunction(ids=>{const rows=[...document.querySelectorAll('#projects [data-project]')].filter(x=>ids.includes(x.dataset.project));return rows.map(x=>x.dataset.project).join()===ids.join();},created.map(p=>p.id));
  await select.selectOption('created-desc');await page.waitForFunction(id=>document.querySelector('#projects [data-project]').dataset.project===id,created[2].id);
  // Native HTML drag reorders only the shelf, and persists across a fresh page.
  await page.locator('#projects [data-project="'+created[0].id+'"]').dragTo(page.locator('#projects [data-project="'+created[2].id+'"]'),{targetPosition:{x:20,y:4}});
  await page.waitForFunction(id=>document.querySelector('#projects [data-project]').dataset.project===id,created[0].id);
  await page.locator('[data-shelf=music] small').filter({hasText:'排序已保存'}).waitFor();assert.equal((await api('/api/project-library/music')).mode,'manual');
  await page.reload();await page.waitForFunction(id=>document.querySelector('#projects [data-project]')?.dataset.project===id,created[0].id);
  await page.locator('#projects [data-project="'+created[0].id+'"]').click();await page.locator('[data-tab=lyrics]').click();
  const packageResult=await api('/api/lyrics-build/'+created[0].id,{text:'[00:00.10]Hello\n[00:00.50]World\n',translation:'[00:00.10]你好\n[00:00.50]世界\n',romaji:'[00:00.10]he lo\n[00:00.50]world\n'});
  assert.deepEqual(packageResult.exports.map(x=>x.role),['reading','original','translation','romaji','bilingual']);assert.ok(packageResult.sourceFile.endsWith(path.join('Lyrics 001','Source.json')));
  await page.reload();await page.locator('[data-tab=lyrics]').click();await page.locator('.lyric-downloads').filter({hasText:'双语 LRC'}).waitFor();
  assert.match(await page.locator('.lyric-downloads code').textContent(),/exports[\\/]lyrics/);
  for(const entry of packageResult.exports){const r=await page.request.get(base+entry.url);assert.ok(r.ok());assert.match(r.headers()['content-disposition'],/attachment/);assert.ok((await r.body()).length>10);assert.ok(!path.basename(entry.file).includes(created[0].id));}
  const downloadPromise=page.waitForEvent('download');await page.locator('.lyric-downloads a').filter({hasText:'下载原文 LRC'}).click();const download=await downloadPromise;assert.match(download.suggestedFilename(),/Shelf Alpha.*Original\.lrc/);
  let opened=null;await page.route('**/api/daw-open/new',r=>{opened=r.request().postDataJSON();return r.fulfill({json:{ok:true}});});await page.locator('#openLyricFolder').click();await page.waitForTimeout(100);assert.equal(opened.path,packageResult.outputDirectory);
  await page.locator('#saveReadings').click();await page.locator('.lyric-downloads a').first().filter({hasText:'原文＋罗马音'}).waitFor();
  for(const p of created)await fs.access(p.working);
  const video=await api('/api/video-create/new',{name:'Shelf Standalone Video'}),location=(await api('/api/video-project/'+encodeURIComponent(video.id))).folder;assert.equal(location,path.join(root,'projects','Shelf Standalone Video','video',video.id));
  assert.ok(!await fs.stat(path.join(root,'projects/video')).catch(()=>false));
  await page.screenshot({path:'reports/project-library-lyrics.png'});await page.setViewportSize({width:390,height:844});assert.ok(!await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2));assert.deepEqual(errors,[]);
  console.log('PASS: shelf date sorting/native drag/persistence, readable original/translation/romaji/bilingual downloads, saved-folder reveal, revision history, standalone video ownership and mobile layout');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
