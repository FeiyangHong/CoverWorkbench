/* Cache static subtitle layers instead of approximating libass with CSS fonts. */
(() => {
'use strict';
const cache=new Map(),status=document.querySelector('#captionRenderStatus');
let enabled=false,closed=false,busy='',demand=null,timer=null,controller=null;
const keyOf=payload=>JSON.stringify(payload);
function note(text,approximate=false){status.textContent=text;status.classList.toggle('approximate',approximate);}
function queue(payload,redraw,prefetch=false){
 const key=keyOf(payload);
 if(closed||cache.get(key)?.image||cache.get(key)?.error||busy===key)return;
 if(prefetch&&(demand||busy))return;
 if(demand?.key===key)return;
 demand={payload,key,redraw};clearTimeout(timer);timer=setTimeout(run,prefetch?0:140);
}
async function run(){
 if(closed||busy||!demand)return;
 const task=demand;demand=null;busy=task.key;controller=new AbortController();
 try{
  let result=cache.get(task.key);
  if(!result?.url){const response=await fetch('/api/video-caption/new',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(task.payload),signal:controller.signal});result=await response.json();if(!response.ok)throw Error(result.error||'字幕排版暂不可用');}
  const image=new Image();image.alt='';image.src=result.url;await image.decode();
  cache.delete(task.key);cache.set(task.key,{image,url:result.url});
  // Retain only three decoded canvases, rather than a song's worth of RGBA images.
  const decoded=[...cache.values()].filter(item=>item.image);decoded.slice(0,-3).forEach(item=>delete item.image);
 }catch(error){if(!closed)cache.set(task.key,{error:error.message,retryAt:Date.now()+5000});}
 finally{
  busy='';controller=null;
  while(cache.size>128)cache.delete(cache.keys().next().value);
  if(!closed){task.redraw();if(demand){clearTimeout(timer);timer=setTimeout(run,0);}}
 }
}
window.CWCaptionPreview={
 configure(value){enabled=Boolean(value);},
 clear(overlay,rendered=false){overlay.replaceChildren();delete overlay.dataset.captionKey;note(rendered?'字幕已随视频渲染':enabled?'字幕排版 · 与成片同源':'字幕近似显示 · 需配置 FFmpeg',!enabled&&!rendered);},
 paint(overlay,payload,geometry,redraw){
  if(!enabled){note('字幕近似显示 · 需配置 FFmpeg',true);return false;}
  const key=keyOf(payload);let item=cache.get(key);
  if(item?.error&&Date.now()>item.retryAt){cache.delete(key);item=null;}
  if(item?.error){note('字幕近似显示 · 本机排版暂不可用，请使用准确预览',true);return false;}
  if(item?.image){
   cache.delete(key);cache.set(key,item);
   const image=item.image;
   Object.assign(image.style,{left:geometry.left+'px',top:geometry.top+'px',width:geometry.width+'px',height:geometry.height+'px'});
   if(overlay.dataset.captionKey!==key){overlay.replaceChildren(image);overlay.dataset.captionKey=key;}
   note('字幕排版 · 与成片同源');return true;
  }
  overlay.replaceChildren();delete overlay.dataset.captionKey;note('正在更新成片字幕…');queue(payload,redraw);return true;
 },
 prefetch(payload,redraw){if(enabled&&payload.cues.length)queue(payload,redraw,true);}
};
window.addEventListener('cw-workbench-exit',()=>{closed=true;clearTimeout(timer);demand=null;controller?.abort();});
})();
