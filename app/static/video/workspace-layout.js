/* View preferences and panel routing never write creative project data. */
(() => {
'use strict';
const ui=window.CWVideoStudio,$=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
let project='',mode='captions',height=280,table=true,hadPicture=null;
const read=key=>{try{return JSON.parse(localStorage.getItem(key));}catch{return null;}};
const write=(key,value)=>{try{localStorage.setItem(key,JSON.stringify(value));}catch{}};
const key=()=> 'cw-video-view:'+project;
function section(id,title){const el=document.createElement('section');el.id=id;el.className='settings-panel';el.hidden=true;const h=document.createElement('h2');h.textContent=title;el.append(h);$('.inspector').append(el);return el;}
const sound=section('sound','音乐、对齐与响度'),subtitles=section('subtitleSource','字幕来源'),picture=section('pictureSettings','画布与片段');
const sources=$('#sources');$('#sources > h2').textContent='参考视频与下载';$('#video').closest('label').firstChild.textContent='参考视频（对时 / 整段 MV）';const lines=$$('#sources > hr'),audio=$('#audio').closest('label');sound.append(audio);sound.prepend($('#audioSource').closest('label'));
let el=lines[0].nextElementSibling;
while(el&&el!==lines[1]){const next=el.nextElementSibling;sound.append(el);el=next;}
el=lines[1].nextElementSibling;
while(el){const next=el.nextElementSibling;subtitles.append(el);el=next;}
lines.forEach(el=>el.remove());
picture.append($('.edit-project-settings'),$('#editInspector'));
const libraryPanel=section('library','项目媒体库');libraryPanel.append($('#editLibrary'));
$('#editLibrary > hr')?.remove();
const download=$('#url').closest('details');download.id='videoDownload';download.open=true;
$('#layout > h2').textContent='字幕样式';$('#output > h2').textContent='导出设置';
$('.inspector-tabs').innerHTML=[['library','媒体库'],['sources','参考/下载'],['sound','声音'],['subtitleSource','字幕'],['pictureSettings','片段'],['layout','样式'],['output','导出']].map(([id,label])=>`<button type="button" data-panel="${id}" role="tab" aria-controls="${id}">${label}</button>`).join('');
function panel(name,target=null){
 if(target){const element=$(target);name=element?.closest('.settings-panel')?.id||name;}
 if(name==='pictureSettings'&&!ui.peek().doc?.composition)name='sources';
 $$('[data-panel]').forEach(b=>{const active=b.dataset.panel===name;b.classList.toggle('active',active);b.setAttribute('aria-selected',String(active));});
 $$('.settings-panel').forEach(p=>p.hidden=p.id!==name);$('.inspector').scrollTop=0;
 if(name==='layout'||name==='subtitleSource')focus('captions');
 if(name==='pictureSettings')focus('picture');
 if(target){const element=$(target);if(element?.matches('input'))element.focus({preventScroll:true});}
}
$$('[data-panel]').forEach(b=>b.onclick=()=>panel(b.dataset.panel));
const workflow=document.createElement('details');workflow.id='workflowDetails';workflow.innerHTML='<summary>步骤检查 <span id="workflowSummary">查看缺项与对齐状态</span></summary>';
$('#videoGuide').before(workflow);workflow.append($('#videoGuide'));
new MutationObserver(()=>{const heading=$('#videoGuide .guide-heading span:not(.eyebrow)');if(heading)$('#workflowSummary').textContent=heading.textContent;}).observe($('#videoGuide'),{childList:true,subtree:true});
const toolbar=document.createElement('div');toolbar.className='editor-view-toolbar';toolbar.innerHTML='<div class="editor-view-tabs" role="group" aria-label="编辑视图"><button type="button" class="quiet" data-editor-focus="picture">画面剪辑</button><button type="button" class="quiet" data-editor-focus="captions">字幕编辑</button><button type="button" class="quiet" data-editor-focus="overview">总览</button></div><label class="preview-size">画面大小<input id="previewSize" type="range" min="180" max="600" step="20" aria-label="预览画面高度"><output id="previewSizeValue"></output></label><label class="check caption-table-switch"><input id="captionTableToggle" type="checkbox" checked>字幕表</label>';
$('.preview-card').prepend(toolbar);
const monitor=document.createElement('div');monitor.className='preview-monitor';$('.preview-card').prepend(monitor);for(const el of [toolbar,$('.preview-card > .preview-head'),$('#stage'),$('#cover'),$('.transport')])monitor.append(el);$('#subtitleTimeline').after($('.timeline-card'));

$('#previewTitle').textContent='预览';$('.preview-head .eyebrow').remove();
$('.timeline-card h2').textContent='字幕文字与时间';$('.timeline-card .eyebrow')?.remove();
const status=document.createElement('small');status.id='picturePreviewStatus';status.setAttribute('role','status');$('#captionRenderStatus').after(status);
new MutationObserver(()=>{const buffering=$('#editTransitionCanvas').dataset.buffering==='true'&&!$('#editTransitionCanvas').hidden;status.textContent=buffering?'画面缓冲中 · 保留已解码画面':'';}).observe($('#editTransitionCanvas'),{attributes:true,attributeFilter:['data-buffering','hidden']});
function persist(){write(key(),{mode,height,table});}
function focus(value){
 mode=value==='picture'&&!ui.peek().doc?.composition?'captions':value;
 document.body.dataset.editorFocus=mode;document.body.classList.toggle('show-caption-table',table);
 $$('button[data-editor-focus]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.editorFocus===mode)));
 $('#captionTableToggle').checked=table;persist();requestAnimationFrame(()=>{ui.redraw();window.dispatchEvent(new Event('cw-video-layout'));});
}
function size(value){height=Math.max(180,Math.min(600,Number(value)||280));document.documentElement.style.setProperty('--preview-height',height+'px');$('#previewSize').value=height;$('#previewSizeValue').textContent=height+' px';persist();ui.redraw();}
$$('button[data-editor-focus]').forEach(b=>b.onclick=()=>focus(b.dataset.editorFocus));
$('#previewSize').oninput=e=>size(e.target.value);
$('#captionTableToggle').onchange=e=>{table=e.target.checked;focus(mode);};
const menu=document.createElement('details');menu.className='video-document-menu';menu.innerHTML='<summary>工程与帮助</summary><div><select id="videoProjectSelect" aria-label="切换视频工程"></select><button type="button" class="quiet" data-video-command="editNew">新建剪辑工程</button><button type="button" class="quiet" data-video-command="editCopy">以当前工程创建剪辑副本</button><button type="button" class="quiet" data-video-command="new">新建完整 MV 工程</button><button type="button" class="quiet" data-video-command="legacy">导入现有配置</button><button type="button" class="quiet" id="videoUsageToggle">剪辑操作说明</button></div>';
$('.document-bar > div:last-child').prepend(menu);
$$('[data-video-command]').forEach(b=>b.onclick=()=>{menu.open=false;$('#'+b.dataset.videoCommand).click();});
$('#videoUsageToggle').onclick=()=>{menu.open=false;$('#editUsage').open=!$('#editUsage').open;$('#editUsage').scrollIntoView({block:'nearest'});};
$('#videoProjectSelect').onchange=e=>{$('#projects').value=e.target.value;$('#projects').dispatchEvent(new Event('change'));menu.open=false;};
function catalog(){$('#videoProjectSelect').innerHTML=$('#projects').innerHTML;$('#videoProjectSelect').value=ui.peek().doc?.id||'';}
function opened(){
 const doc=ui.peek().doc;if(!doc)return;const pictureChanged=project===doc.id&&hadPicture!==null&&hadPicture!==!!doc.composition;hadPicture=!!doc.composition;document.body.classList.add('has-document');
 if(project!==doc.id){project=doc.id;const pref=read(key())||{};table=pref.table!==false;size(pref.height||280);focus(['picture','captions','overview'].includes(pref.mode)?pref.mode:doc.composition?'picture':'captions');panel('library');workflow.open=false;}
 if(!doc.composition&&mode==='picture')focus('captions');else if(pictureChanged&&doc.composition)focus('picture');
 $('button[data-editor-focus="picture"]').hidden=!doc.composition;$('[data-panel="pictureSettings"]').hidden=!doc.composition;catalog();
}
// Route contextual actions to their actual panel, including hidden source fields.
document.addEventListener('click',e=>{const b=e.target.closest('[data-guide-action]');if(!b)return;const action=b.dataset.guideAction;
 if(action==='table'){focus('captions');table=true;focus(mode);}
 if(['audio','analyze','listen-mix'].includes(action))panel('sound');
 if(action==='captions')panel('subtitleSource');
 if(['video','download'].includes(action))panel('sources');if(action==='library')panel('library');
},true);
$('#editCanvas').addEventListener('dblclick',e=>{if(e.target.closest('[data-picture]'))panel('pictureSettings');},true);
window.addEventListener('cw-video-change',e=>{if(['document','open','history'].includes(e.detail.type))opened();if(e.detail.type==='catalog')catalog();});
window.CWVideoView={panel,focus,size,showTable:()=>{table=true;focus('captions');}};
ui.ready.then(opened);
})();
