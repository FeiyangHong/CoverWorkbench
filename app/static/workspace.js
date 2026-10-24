/* One application shell, with a persistent, lazily mounted video editor. */
(() => {
'use strict';
const $=s=>document.querySelector(s),tabs=[...document.querySelectorAll('.tabs [data-tab]')];
let frame=null,editor=null,active=false,lastMusic='workflow',metadata=null,metadataKey='',pendingProject=null,navigating=false,restoring=false,exited=false;
const shelf=$('#videoProjectShelf'),list=$('#videoProjects'),count=$('#videoProjectCount'),title=$('#videoProjectTitle');
function route(tab,project,replace=false){const url=new URL(location.href);if(url.searchParams.get('tab')===tab&&(url.searchParams.get('videoProject')||null)===(tab==='video'?project||null:null))return;url.searchParams.set('tab',tab);if(tab==='video'&&project)url.searchParams.set('videoProject',project);else url.searchParams.delete('videoProject');if(url.href!==location.href)history[replace?'replaceState':'pushState']({},'',url);}
function chrome(){
 document.body.classList.toggle('is-video-workspace',active);shelf.hidden=!active;
 document.querySelectorAll('[data-workspace]').forEach(b=>b.setAttribute('aria-current',(b.dataset.workspace==='video')===active?'page':'false'));
 title.textContent=metadata?.name||'视频制作';document.title=active?(metadata?.name?metadata.name+' · ':'')+'视频制作 · CoverWorkbench':'CoverWorkbench';
}
function publish(data){
 const key=JSON.stringify(data);metadata=data;if(key!==metadataKey){metadataKey=key;count.textContent=data.projects.length;list.replaceChildren();
  if(!data.projects.length){const note=document.createElement('p');note.className='video-library-empty';note.textContent='新建视频工程，开始第一支作品。';list.append(note);}
  for(const p of data.projects){const b=document.createElement('button');b.type='button';b.className='project-item'+(p.id===data.id?' active':'');b.dataset.videoProject=p.id;const badge=document.createElement('span');badge.className='cover video-cover';badge.textContent='▷';const label=document.createElement('span'),name=document.createElement('strong'),detail=document.createElement('small');name.textContent=p.name;detail.textContent=p.id===data.id?(data.dirty?'有未保存修改':'正在编辑 · r'+p.revision):'视频工程 · r'+p.revision;label.append(name,detail);b.append(badge,label);b.onclick=()=>navigate(p.id);list.append(b);}
 }
 chrome();if(active&&!navigating&&(!pendingProject||data.id===pendingProject)&&data.id)route('video',data.id,true);
}
async function navigate(id){
 pendingProject=id;if(!editor||navigating)return;navigating=true;let failed=false;
 try{await editor.navigate(id);}
 catch(e){failed=true;toast(e.message);}
 finally{navigating=false;if(pendingProject&&pendingProject!==id){navigate(pendingProject);return;}pendingProject=null;if(active)route('video',editor.state().id,failed);}
}
function mount(){
 if(frame)return;frame=document.createElement('iframe');frame.id='videoWorkspaceFrame';frame.title='视频制作工作区';frame.setAttribute('allow','autoplay');
 const url=new URL('/video/index.html',location.origin);url.searchParams.set('embed','1');if(pendingProject)url.searchParams.set('project',pendingProject);frame.src=url;
 $('#videoMount').append(frame);$('#videoLoading').hidden=false;
}
function revealTab(){const nav=$('.tabs'),button=nav.querySelector('.active');if(!button)return;const box=button.getBoundingClientRect(),bounds=nav.getBoundingClientRect();if(box.left<bounds.left)nav.scrollLeft-=bounds.left-box.left;else if(box.right>bounds.right)nav.scrollLeft+=box.right-bounds.right;}
new ResizeObserver(revealTab).observe($('.tabs'));
function activate(tab,write=true){
 active=tab==='video';if(!active)lastMusic=tab;chrome();revealTab();
 if(active){audio.pause();mount();}editor?.visible(active);
 if(write&&!restoring)route(tab,active?pendingProject||metadata?.id:null);
}
window.CWVideoHost={
 update:publish,
 ready(api){editor=api;$('#videoLoading').hidden=true;$('#videoNewProject').disabled=false;editor.visible(active);if(pendingProject&&editor.state().id!==pendingProject)navigate(pendingProject);else pendingProject=null;publish(editor.state());},
 open(id){if(id)pendingProject=id;$('.tabs [data-tab="video"]').click();if(id&&editor)navigate(id);}
};
window.addEventListener('cw-workspace-change',e=>activate(e.detail.tab,!e.detail.restore));
document.querySelectorAll('[data-workspace]').forEach(b=>b.onclick=()=>{const tab=b.dataset.workspace==='video'?'video':lastMusic;const button=$('.tabs [data-tab="'+tab+'"]');(button&&!button.disabled?button:$('.tabs [data-tab="daw"]')).click();});
$('#videoNewProject').onclick=()=>editor?.create();
function restoreRoute(){const url=new URL(location.href),tab=url.searchParams.get('tab')||($('.tabs [data-tab="workflow"]').disabled?'daw':'workflow');if(!tabs.some(b=>b.dataset.tab===tab))return;pendingProject=tab==='video'?url.searchParams.get('videoProject'):null;const button=$('.tabs [data-tab="'+tab+'"]');if(button.disabled)return;button.click();if(active&&pendingProject&&editor)navigate(pendingProject);}
// Clicking a tab normally creates history; browser back/forward must only restore it.
window.addEventListener('popstate',()=>{restoring=true;try{restoreRoute();}finally{restoring=false;}});
window.addEventListener('cw-environment-changed',()=>editor?.refresh().catch(e=>toast(e.message)));
window.addEventListener('beforeunload',e=>{if(!exited&&editor?.state().dirty){e.preventDefault();e.returnValue='';}});
window.addEventListener('cw-workbench-exit',()=>{exited=true;frame?.contentWindow.dispatchEvent(new Event('cw-workbench-exit'));});
document.addEventListener('keydown',e=>{if(!active||!editor||e.defaultPrevented||e.isComposing||document.querySelector('dialog[open]'))return;const target=e.target;if(target.matches?.('input,textarea,select,[contenteditable=true]'))return;if(e.ctrlKey&&e.key.toLowerCase()==='s'){e.preventDefault();editor.save().catch(e=>toast(e.message));}else if(e.ctrlKey&&['z','y'].includes(e.key.toLowerCase())){e.preventDefault();editor[e.key.toLowerCase()==='y'||e.shiftKey?'redo':'undo']();}});
const initial=new URL(location.href),initialTab=initial.searchParams.get('tab');if(tabs.some(b=>b.dataset.tab===initialTab)){pendingProject=initialTab==='video'?initial.searchParams.get('videoProject'):null;$('.tabs [data-tab="'+initialTab+'"]').click();}
})();
