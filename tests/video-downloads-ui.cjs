/* Download titles and separate media/task locations on a disposable server only. */
const {chromium}=require('playwright'),assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs/promises');
(async()=>{
 const base=process.argv[2],browser=await chromium.launch({headless:true,...(process.env.CW_BROWSER_CHANNEL?{channel:process.env.CW_BROWSER_CHANNEL}:{})});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  async function api(url,body){const r=await context.request[body===undefined?'get':'post'](base+url,body===undefined?{}:{data:body});const x=await r.json();assert.ok(r.ok(),JSON.stringify(x));return x;}
  const root=(await api('/api/health')).root;assert.ok(path.resolve(root).startsWith(path.resolve(__dirname,'../work')+path.sep)&&path.basename(root).startsWith('portable checkout '));
  const doc=await api('/api/video-create/new',{name:'Synthetic Download Layout'}),folder=(await api('/api/video-project/'+encodeURIComponent(doc.id))).folder;
  const name='合成歌手 - テスト曲 (Official Video).mkv',media=path.join(folder,'Media/Video',name),tasks=path.join(folder,'Tasks/Download 006'),legacy=path.join(folder,'Jobs/Download 005'),old=path.join(legacy,'source.mkv');
  await fs.mkdir(path.dirname(media),{recursive:true});await fs.mkdir(tasks,{recursive:true});await fs.mkdir(legacy,{recursive:true});await fs.writeFile(media,'synthetic titled media');await fs.writeFile(old,'unchanged legacy media');
  const record={id:'a'.repeat(32),kind:'download',project:doc.id,status:'completed',stage:'完成',version:6,created:Date.now()/1000,folder:tasks,files:['info.json','provenance.json'],result:{path:media,name,title:name.slice(0,-4)}};
  const oldRecord={...record,id:'b'.repeat(32),version:5,created:record.created-100,folder:legacy,files:['source.mkv','provenance.json'],result:{path:old}};
  await fs.writeFile(path.join(tasks,'job.json'),JSON.stringify(record));await fs.writeFile(path.join(legacy,'job.json'),JSON.stringify(oldRecord));
  await page.goto(base+'/video/index.html?standalone=1&project='+encodeURIComponent(doc.id));await page.locator('.job-filename').filter({hasText:name}).waitFor();assert.equal(await page.locator('.job-filename').count(),2);assert.equal(await page.locator('.job a').count(),0,'Private metadata was exposed as a media download');
  await page.route('**/api/daw-open/*',r=>r.fulfill({json:{opened:true}}));
  async function openFolder(selector,target){const sent=page.waitForRequest(r=>r.url().includes('/api/daw-open/'));await page.locator(selector).click();assert.deepEqual((await sent).postDataJSON(),{action:'folder',path:target});}
  await openFolder('[data-folder="'+record.id+'"]',media);
  await openFolder('[data-task-folder="'+record.id+'"]',tasks);
  await openFolder('[data-folder="'+oldRecord.id+'"]',old);
  assert.equal((await api('/api/video-project/'+encodeURIComponent(doc.id))).project.revision,1);assert.equal(await fs.readFile(old,'utf8'),'unchanged legacy media');
  await page.setViewportSize({width:390,height:844});assert.ok(!await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2));assert.deepEqual(errors,[]);
  console.log('PASS: website-titled download cards, separate media/task folder actions, hidden metadata links, legacy record compatibility and unchanged project/old media');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
