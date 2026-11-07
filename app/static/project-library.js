/* Shared music/video shelves. Preferences are local to this installation, not this tab. */
(() => {
'use strict';
async function request(kind,body){const r=await fetch('/api/project-library/'+kind,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{}),d=await r.json();if(!r.ok)throw Error(d.error||'读取排序失败');return d;}
for(const [kind,id,attribute] of [['music','projects','data-project'],['video','videoProjects','data-video-project']]){
 const list=document.getElementById(id),bar=document.createElement('div');bar.className='project-sort';bar.dataset.shelf=kind;
 bar.innerHTML='<select aria-label="'+(kind==='music'?'本机工程':'视频工程')+'排序"><option value="updated-desc">最近修改 · 新到旧</option><option value="updated-asc">最近修改 · 旧到新</option><option value="created-desc">创建时间 · 新到旧</option><option value="created-asc">创建时间 · 旧到新</option><option value="name">名称排序</option><option value="manual">自定义拖拽排序</option></select><small role="status">拖动项目即可自定义；Alt + ↑ / ↓ 移动</small>';list.before(bar);
 let data={mode:'updated-desc',order:[],rows:[]},drag=null,saving=false,again=false,serial=0,reads=0,videoVersion='';
 const select=bar.querySelector('select'),hint=bar.querySelector('small');
 const rows=()=>[...list.children].filter(x=>x.hasAttribute(attribute));
 function paint(){
  observer.disconnect();select.value=data.mode;const metadata=new Map(data.rows.map(p=>[p.id,p])),rank=new Map(data.order.map((v,i)=>[v,i]));
  const sorted=rows().sort((a,b)=>{const x=metadata.get(a.getAttribute(attribute))||{},y=metadata.get(b.getAttribute(attribute))||{};if(data.mode==='manual')return (rank.get(a.getAttribute(attribute))??1e9)-(rank.get(b.getAttribute(attribute))??1e9);if(data.mode==='name')return a.textContent.localeCompare(b.textContent,'zh-CN');const [key,direction]=data.mode.split('-');return ((x[key]||0)-(y[key]||0))*(direction==='desc'?-1:1)||a.textContent.localeCompare(b.textContent,'zh-CN');});
  for(const item of sorted){item.draggable=true;item.title='拖拽排序；Alt + ↑ / ↓ 移动';list.append(item);}
  observer.observe(list,{childList:true});
 }
 async function persist(){serial++;if(saving){again=true;return;}saving=true;const body={mode:data.mode,order:[...data.order]};try{await request(kind,body);hint.textContent='排序已保存 · 拖拽或 Alt + ↑ / ↓ 移动';}catch(e){hint.textContent=e.message;}finally{saving=false;if(again){again=false;persist();}}}
 function move(item,target,after){const ordered=rows().filter(x=>x!==item),index=ordered.indexOf(target);if(index<0)return;ordered.splice(index+(after?1:0),0,item);data.order=ordered.map(x=>x.getAttribute(attribute));data.mode='manual';paint();persist();}
 const observer=new MutationObserver(()=>{paint();if(rows().some(x=>!data.rows.some(p=>p.id===x.getAttribute(attribute))))refresh();});observer.observe(list,{childList:true});
 select.onchange=()=>{data.mode=select.value;if(data.mode==='manual'&&!data.order.length)data.order=rows().map(x=>x.getAttribute(attribute));paint();persist();};
 list.addEventListener('dragstart',e=>{drag=e.target.closest('['+attribute+']');if(!drag)return;e.dataTransfer.setData('text/plain',drag.getAttribute(attribute));e.dataTransfer.effectAllowed='move';drag.classList.add('shelf-dragging');});
 list.addEventListener('dragover',e=>{if(drag){e.preventDefault();e.dataTransfer.dropEffect='move';}});
 list.addEventListener('drop',e=>{const target=e.target.closest('['+attribute+']');if(!drag||!target||target===drag)return;e.preventDefault();move(drag,target,e.clientY>target.getBoundingClientRect().top+target.clientHeight/2);});
 list.addEventListener('dragend',()=>{drag?.classList.remove('shelf-dragging');drag=null;});
 list.addEventListener('keydown',e=>{if(!e.altKey||!['ArrowUp','ArrowDown'].includes(e.key))return;const item=e.target.closest('['+attribute+']'),all=rows(),target=all[all.indexOf(item)+(e.key==='ArrowUp'?-1:1)];if(!target)return;e.preventDefault();move(item,target,e.key==='ArrowDown');item.focus();});
 async function refresh(){const before=serial,ticket=++reads;try{const result=await request(kind);if(ticket!==reads)return;data=before===serial&&!saving?result:{...data,rows:result.rows};paint();}catch(e){hint.textContent=e.message;}}
 window.addEventListener('cw-library-refresh',refresh);window.addEventListener('focus',refresh);
 if(kind==='music')window.addEventListener('cw-music-project-change',refresh);
 else window.addEventListener('cw-video-project-state',e=>{const version=JSON.stringify(e.detail.projects.map(p=>[p.id,p.revision]));if(version!==videoVersion){videoVersion=version;refresh();}});
 refresh();
}
})();
