/* Viewport-only thumbnail sheets; decoding never writes the creative document. */
(() => {
'use strict';
const ui=window.CWVideoStudio,$=s=>document.querySelector(s),sheets=new Map(),queue=[];
let timer=0,working=0,generation=0,project='',enabled=true;
try{enabled=localStorage.getItem('cw-filmstrips')!=='off';}catch{}
function clearQueued(){for(const entry of queue)sheets.delete(entry.key);queue.length=0;}
function setEnabled(value){if(!value)clearQueued();else for(const [key,entry] of sheets)if(entry.error)sheets.delete(key);enabled=value;$('#editFilmstrip').checked=value;document.body.classList.toggle('hide-filmstrips',!value);try{localStorage.setItem('cw-filmstrips',value?'on':'off');}catch{}schedule();}
$('#editFilmstrip').onchange=e=>setEnabled(e.target.checked);
function request(asset,level,bucket){
 const doc=ui.peek().doc,key=[doc.id,asset.id,asset.path,level,bucket].join('|');let record=sheets.get(key);
 if(record){sheets.delete(key);sheets.set(key,record);return record;}
 record={key,asset:asset.id,level,bucket,project:doc.id,generation,loading:true};sheets.set(key,record);queue.push(record);
 while(sheets.size>160)sheets.delete(sheets.keys().next().value);pump();return record;
}
function pump(){while(working<2&&queue.length){const entry=queue.shift();if(entry.generation!==generation||!enabled){sheets.delete(entry.key);continue;}working++;
 ui.api('/api/video-filmstrip/'+encodeURIComponent(entry.project),{asset:entry.asset,level:entry.level,bucket:entry.bucket}).then(result=>entry.data=result).catch(e=>entry.error=/Unknown action/i.test(e.message)?'重启后台以加载缩略图功能':/ffmpeg|未配置|找不到/i.test(e.message)?'缩略图需配置 FFmpeg':e.message).finally(()=>{entry.loading=false;working--;if(entry.generation===generation)schedule();pump();});
}}
function schedule(){clearTimeout(timer);timer=setTimeout(paint,90);}
function paint(){
 const doc=ui.peek().doc;if(!doc?.composition||!ui.get().visible)return;
 if(project!==doc.id){project=doc.id;generation++;queue.length=0;sheets.clear();}
 if(!enabled)return;
 const comp=doc.composition,canvas=$('#editCanvas'),scroll=$('#editScroll'),viewport=scroll.getBoundingClientRect(),box=canvas.getBoundingClientRect(),pps=canvas.clientWidth/comp.duration;
 const start=Math.max(0,(viewport.left-box.left)/pps),end=Math.min(comp.duration,(viewport.right-box.left)/pps);
 for(const el of canvas.querySelectorAll('[data-picture]')){
  const clip=comp.clips.find(c=>c.id===el.dataset.picture),strip=el.querySelector('.clip-filmstrip'),asset=clip&&comp.assets.find(a=>a.id===clip.asset);if(!asset||!strip)continue;
  const vertical=el.getBoundingClientRect();if(clip.start>=end||clip.start+clip.duration<=start||vertical.bottom<0||vertical.top>innerHeight){strip.replaceChildren();continue;}
  const level=Math.max(0,Math.min(20,Math.round(Math.log2(96/pps/.04)))),step=.04*2**level;
  const from=Math.max(0,Math.floor((clip.in+Math.max(0,start-clip.start))/step)),last=Math.ceil((clip.in+Math.min(clip.duration,end-clip.start))/step),parts=[];let loading=false,error='';
  for(let n=from;n<=last&&parts.length<100;n++){
   const source=n*step;if(asset.kind==='video'&&source>=asset.duration||source>=clip.in+clip.duration)break;
   const x=(source-clip.in)*pps,width=step*pps,cell=document.createElement('span');cell.className='filmstrip-cell';cell.style.left=x+'px';cell.style.width=(width+.5)+'px';cell.dataset.sourceTime=source.toFixed(3);
   if(asset.kind==='image'){cell.style.backgroundImage=`url("/video-edit-media/${encodeURIComponent(doc.id)}/${asset.id}/${asset.thumbnail?'thumb':'original'}")`;cell.style.backgroundSize='cover';cell.style.backgroundPosition='center';}
   else{
    const bucket=Math.floor(n/8),entry=request(asset,level,bucket);loading||=entry.loading;error=entry.error||error;
    if(entry.data){const index=n%8;cell.style.backgroundImage=`url("${entry.data.url}")`;cell.style.backgroundPosition=(index%4/3*100)+'% '+(Math.floor(index/4)*100)+'%';}
   }
   parts.push(cell);
  }
  if(loading||error){const status=document.createElement('span');status.className='filmstrip-status';status.textContent=error||'正在生成画面…';status.title=error;parts.push(status);}
  strip.replaceChildren(...parts);el.dataset.filmstripLevel=String(level);
 }
}
$('#editScroll').addEventListener('scroll',schedule,{passive:true});
window.addEventListener('scroll',schedule,{passive:true,capture:true});
window.addEventListener('cw-picture-render',schedule);window.addEventListener('cw-video-layout',schedule);window.addEventListener('cw-video-change',e=>{if(e.detail.type==='visibility'&&!ui.get().visible)clearQueued();if(['open','visibility'].includes(e.detail.type))schedule();});
window.addEventListener('cw-workbench-exit',()=>{generation++;queue.length=0;clearTimeout(timer);});
setEnabled(enabled);ui.ready.then(schedule);
window.CWFilmstrips={schedule};
})();
