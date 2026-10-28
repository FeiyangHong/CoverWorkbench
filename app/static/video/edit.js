/* A picture edit has its own clock. Music and captions never ripple with picture edits. */
(() => {
'use strict';
const pictureEdits=window.CWPictureEdits;
const ui=window.CWVideoStudio,$=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let projectId='',library=[],selected=null,position=0,playing=false,started=0,origin=0,animation=null,loaded='',zoom=1,drag=null,effectDrag=null,request=0,closed=false;
let selectedTrack='V1';
let importBusy=false,importStop=false,enableBusy=false,lastImported=[];
const image=document.createElement('img');image.id='editStill';image.alt='图片画面';image.hidden=true;$('#stage').insertBefore(image,$('#overlay'));
const transitionCanvas=document.createElement('canvas');transitionCanvas.id='editTransitionCanvas';transitionCanvas.width=1920;transitionCanvas.height=1080;transitionCanvas.hidden=true;transitionCanvas.setAttribute('aria-label','画面转场预览');$('#stage').insertBefore(transitionCanvas,$('#overlay'));const transitionContext=transitionCanvas.getContext('2d'),transitionMedia=new Map();
const transitionEditor=document.createElement('div');transitionEditor.id='editTransitionEditor';transitionEditor.className='transition-editor';
const welcome=document.createElement('section');welcome.className='edit-entry';welcome.innerHTML='<div><span class="eyebrow">PICTURE YOUR SONG</span><strong>一首完整的歌，不必只有一支 MV。</strong><p>用 OP、ED、PV、图片和自己的视频拼出画面。音乐与字幕独立保留。</p></div><div><button id="editNew">＋ 新建剪辑工程</button><button id="editCopy" class="quiet">以当前工程创建剪辑副本</button></div>';
$('.intro').after(welcome);
const usage=document.createElement('details');usage.className='edit-usage';usage.id='editUsage';usage.innerHTML='<summary>剪辑怎么用？ · 与视频制作共用同一个工作区</summary><p>完整 MV 换音轨继续使用原工程；需要拼接 OP、ED、PV 或自己的素材时，使用剪辑工程。混音、双语字幕、样式、准确预览和导出都在本页。</p><ol><li>新歌点「新建剪辑工程」；旧工程可在媒体库「启用多素材剪辑」，保留字幕与对齐；也可创建独立剪辑副本。已有剪辑工程直接从工程列表打开。</li><li>选择最终混音并保存，按需要使用混音时长。导入双语字幕，确认时间基准；不要重复添加已经处理过的偏移。</li><li>下载视频后加入媒体库，或「批量导入素材」多选自己的视频、图片；拖动缩略图到画面轨指定秒数，或点「插到播放头」。默认插入排序只顺延画面，也可切换自由移动；支持修剪、分割和排序。</li><li>选择接点添加转场，拖动色带两端调整；单独启用片头淡入或片尾淡出。拖动时画面实时更新，Esc 取消，Ctrl+Z 撤销。</li><li>在同一个预览区检查画面、音乐和双语字幕，再做「准确区间预览」，最后从「导出」面板完整导出。</li></ol><p>音乐和字幕固定在成片时间线上；剪辑与画面淡化不会挪动它们，也不会修改 SV / Studio One 工程。</p>';
welcome.after(usage);
const panel=document.createElement('div');panel.id='editLibrary';panel.hidden=true;panel.innerHTML=`<div class="edit-section-title"><span class="eyebrow">PROJECT MEDIA</span><h2>本曲媒体库</h2><p>外部素材复制入库，项目内素材直接登记。素材保留原声；可切换监听，成片使用选定混音。</p></div><div class="edit-library-actions"><button id="editImport">＋ 导入本地素材</button><button id="editRefresh" class="quiet">刷新</button></div><input id="editSearch" placeholder="搜索素材名称" aria-label="搜索媒体库"><div id="editMedia" class="edit-media"></div><p id="editLibraryStatus" class="hint" role="status"></p><details class="edit-project-settings" open><summary>成片时间与画布</summary><div class="pair"><label>时长 · 秒<input id="editDuration" type="number" min="0.1" max="21600" step="0.04"></label><label>帧率<select id="editFps"><option>24</option><option>25</option><option>30</option><option>60</option></select></label></div><button id="editFitMusic" class="quiet wide">使用混音时长</button><label class="check"><input id="editAllowGaps" type="checkbox">允许空白区间显示黑底</label><p class="hint">16:9 画布 · 默认 1920 × 1080。音乐位置和字幕沿用下方对时设置；剪画面不会改变它们。</p></details><div id="editInspector"></div><hr>`;
$('#sources').prepend(panel);
const timeline=document.createElement('section');timeline.id='editTimeline';timeline.className='picture-timeline';timeline.hidden=true;timeline.innerHTML=`<div class="edit-timeline-heading"><div><h3>画面时间轴</h3></div><div><button class="quiet" data-edit-history="undo">↶ 撤销</button><button class="quiet" data-edit-history="redo">↷ 重做</button></div></div><div class="edit-toolbar"><button id="editSplit" class="quiet">在播放头分割</button><button id="editDuplicate" class="quiet">复制到末尾</button><button id="editEarlier" class="quiet">← 前移</button><button id="editLater" class="quiet">后移 →</button><button id="editDelete" class="quiet">移除 · 留空</button><button id="editRipple" class="quiet">移除并接拢画面</button><button id="editAddTrack" class="quiet">＋ 视频轨</button><label>目标轨<select id="editTargetTrack" aria-label="目标视频轨"></select></label><label class="check"><input id="editFilmstrip" type="checkbox" checked>缩略图</label><label>拖放<select id="editDragMode" aria-label="画面拖放方式"><option value="insert">插入排序</option><option value="move">自由移动</option></select></label><label class="check"><input id="editSnap" type="checkbox" checked>吸附</label><label class="check"><input id="editFollow" type="checkbox" checked>跟随</label><label>缩放 <input id="editZoom" type="range" min="1" max="64" step="0.5" value="1" aria-label="画面时间轴缩放"></label></div><div id="editScroll" class="edit-scroll"><div id="editCanvas" class="edit-canvas"></div></div><p id="editCoverage" class="edit-coverage" role="status"></p><p class="hint">从媒体库拖入视频或图片；插入排序只顺延画面，自由移动放入空隙。拖片段换序，拖两侧修剪；Alt 暂时关闭吸附，Esc 取消。音乐与字幕不挪动。</p>`;
$('#subtitleTimeline').before(timeline);$('#editScroll').after(transitionEditor);
const fadeEditor=document.createElement('div');fadeEditor.id='editFadeEditor';fadeEditor.className='end-fade-editor';transitionEditor.after(fadeEditor);
const effectStatus=document.createElement('p');effectStatus.id='editEffectDragStatus';effectStatus.className='hint effect-drag-status';effectStatus.setAttribute('role','status');fadeEditor.after(effectStatus);
const mediaDialog=document.createElement('dialog');mediaDialog.id='editMediaPreview';mediaDialog.innerHTML='<h2 id="editMediaPreviewTitle"></h2><div id="editMediaPreviewBody"></div><div class="dialog-actions"><button id="editMediaPreviewClose" class="quiet">关闭</button></div>';document.body.append(mediaDialog);
const modeCard=document.createElement('div');modeCard.className='edit-mode-card';modeCard.innerHTML='<strong id="editModeTitle"></strong><p id="editModeNote"></p><button id="editEnable" type="button">启用多素材剪辑</button>';
panel.querySelector('.edit-library-actions').before(modeCard);$('#editImport').textContent='＋ 批量导入素材';
$('#editRefresh').after(Object.assign(document.createElement('button'),{id:'editImportCancel',className:'quiet',textContent:'停止后续',hidden:true}));
const batchAppend=document.createElement('button');batchAppend.id='editAppendImported';batchAppend.className='quiet wide';batchAppend.hidden=true;$('#editSearch').before(batchAppend);
function importControls(){const count=lastImported.filter(a=>a.kind!=='audio').length;$('#editImport').disabled=importBusy||enableBusy;$('#editRefresh').disabled=importBusy;$('#editImportCancel').hidden=!importBusy;$('#editEnable').disabled=importBusy||enableBusy;batchAppend.hidden=!count;batchAppend.disabled=importBusy||enableBusy;batchAppend.textContent='将本次 '+count+' 个画面依次加入末尾';}
async function ensureEdit(){
 if(comp())return false;if(enableBusy)throw Error('正在启用剪辑，请稍候');const id=projectId,at=ui.get().position;enableBusy=true;importControls();$('#editEnable').textContent='正在保留原画面并启用…';
 try{ui.stop();if(state().dirty)await ui.save();if(projectId!==id)return false;const result=await ui.api('/api/video-edit-enable/'+encodeURIComponent(id),{revision:state().doc.revision});if(projectId!==id)return false;await ui.open(id);ui.seek(at);window.CWVideoView?.focus('picture');window.CWVideoView?.panel('library');ui.message('已启用多素材剪辑；字幕、样式、混音与对齐保留。'+(result.warnings||[]).join('；'));return true;
 }finally{enableBusy=false;$('#editEnable').textContent='启用多素材剪辑';importControls();}
}
$('#editEnable').onclick=ui.safe(ensureEdit);$('#editImportCancel').onclick=()=>{importStop=true;$('#editImportCancel').disabled=true;};
async function addToPicture(a,fill=false){const id=projectId,started= a.kind!=='audio'?await ensureEdit():false;if(projectId!==id||a.kind!=='audio'&&!comp())return;if(started&&comp().clips.some(c=>c.asset===a.id||a.sha256&&assetFor(c)?.sha256===a.sha256)){ui.message('原视频已保留在第一段，可继续添加其他画面');return;}append(a,fill);if(a.kind!=='audio')window.CWVideoView?.focus('picture');}
batchAppend.onclick=ui.safe(async()=>{const id=projectId,rows=lastImported.filter(a=>a.kind!=='audio'),started=await ensureEdit();if(projectId!==id||!comp())return;ui.history.begin('批量添加画面');try{for(const a of rows){if(started&&comp().clips.some(c=>c.asset===a.id||a.sha256&&assetFor(c)?.sha256===a.sha256))continue;append(a);}}finally{ui.history.end();}window.CWVideoView?.focus('picture');ui.message('画面已依次接到末尾，音乐和字幕时间保持原位');});
function state(){return ui.peek();}function comp(){return state().doc?.composition;}function active(){return !!comp()&&!state().exact;}
function clock(){return playing?Math.min(comp()?.duration||0,origin+(performance.now()-started)/1000):position;}
function pause(){const wasPlaying=playing;if(playing)position=clock();playing=false;cancelAnimationFrame(animation);ui.player.pause();for(const m of transitionMedia.values())if(m.node.tagName==='VIDEO')m.node.pause();ui.cover.pause();window.CWVideoMonitor?.pause();$('#play').textContent='▶';if(wasPlaying)ui.notify('pause');}
function seek(t){position=Math.max(0,Math.min(comp()?.duration||0,t));if(playing){origin=position;started=performance.now();}sync(true);paintHead();ui.redraw();}
async function toggle(){if(!active())return;if(playing){pause();return;}if($('#listen').value==='cover'){if(!state().doc.audio)throw Error('请先选择最终混音并应用');await ui.startAudio();}else await window.CWVideoMonitor?.prepare();if(clock()>=comp().duration)seek(0);playing=true;origin=position;started=performance.now();$('#play').textContent='Ⅱ';sync(true);ui.notify('play');tick();}
function currentClip(t){return comp()?pictureEdits.front(comp(),t).clip:null;}
function trackOf(c){return pictureEdits.trackOf(c);}
function trackRows(id=selectedTrack){return pictureEdits.clipsOn(comp(),id);}
function trackList(){return pictureEdits.tracks(comp());}
function mediaURL(a,kind='original'){return '/video-edit-media/'+encodeURIComponent(projectId)+'/'+a.id+'/'+kind;}
function transitionRows(){return comp()?pictureEdits.transitions(comp(),true):[];}
function transitionAt(t){return comp()?pictureEdits.front(comp(),t).effect:null;}
function transitionNode(c){
 const a=assetFor(c),key=c.id+':'+a.id+':'+!!a.proxy;let m=transitionMedia.get(key);if(m){transitionMedia.delete(key);transitionMedia.set(key,m);return m.node;}
 const node=document.createElement(a.kind==='image'?'img':'video');if(a.kind==='video'){node.muted=true;node.preload='auto';node.playsInline=true;}
 m={node,key,clip:c.id,frame:null};transitionMedia.set(key,m);
 // Decode callbacks only paint. Seeking from seeked caused repeated seeks and black flashes.
 const paint=()=>{if(active()){const t=pictureTime();if(transitionAt(t)||fadeAlpha(t)<1)presentEffects(t);}};
 node.addEventListener(a.kind==='image'?'load':'loadeddata',paint);
 if(a.kind==='video'){
  node.addEventListener('loadedmetadata',()=>{if(active()){const current=comp().clips.find(x=>x.id===m.clip);if(current&&(transitionAt(pictureTime())||fadeAlpha(pictureTime())<1))positionTransition(current,pictureTime(),true);}});
  node.addEventListener('seeked',paint);
 }
 node.src=mediaURL(a,a.proxy?'proxy':'original');
 if(transitionMedia.size>4){const [oldKey,old]=transitionMedia.entries().next().value;if(old.node.tagName==='VIDEO'){if(!old.node.paused)old.node.pause();old.node.removeAttribute('src');old.node.load();}transitionMedia.delete(oldKey);}
 return node;
}
function preloadTransition(t){const upcoming=pictureEdits.transitions(comp()).find(tr=>tr.end>t&&tr.start<t+2);if(upcoming){transitionNode(upcoming.left);transitionNode(upcoming.right);}}
function positionTransition(c,t,force){
 const node=transitionNode(c);if(node.tagName!=='VIDEO')return node;
 const desired=c.in+Math.max(0,Math.min(t-c.start,c.duration-1/comp().fps)),moving=playing&&t>=c.start&&t<c.start+c.duration-1/comp().fps;
 const tolerance=moving&&!force?.22:.015;
 if(node.readyState>=1&&!node.seeking&&Math.abs(node.currentTime-desired)>tolerance)node.currentTime=desired;
 if(moving&&!node.seeking){if(node.paused)node.play().catch(()=>{});}else if(!node.paused)node.pause();return node;
}
function pictureTime(){return Math.floor((clock()+.000001)*comp().fps)/comp().fps;}
function fadeAlpha(t){const fps=comp().fps,frame=Math.round(t*fps),total=Math.round(comp().duration*fps),f=comp().fades||{};let alpha=1;for(const key of ['in','out']){const n=Math.round((f[key]||0)*fps);if(n>=2)alpha*=Math.max(0,Math.min(1,(key==='in'?frame:total-1-frame)/(n-1)));}return alpha;}
function clipFrame(c){
 const node=transitionNode(c),m=[...transitionMedia.values()].find(x=>x.node===node),w=node.videoWidth||node.naturalWidth,h=node.videoHeight||node.naturalHeight;
 const ready=node.tagName==='VIDEO'?node.readyState>=2&&!node.seeking:node.complete&&w>0;
 if(ready&&w&&h){
  m.frame??=document.createElement('canvas');if(m.frame.width!==1920){m.frame.width=1920;m.frame.height=1080;}
  const ctx=m.frame.getContext('2d'),k=c.fit==='cover'?Math.max(1920/w,1080/h):Math.min(1920/w,1080/h),dw=w*k,dh=h*k;
  ctx.fillStyle='#000';ctx.fillRect(0,0,1920,1080);ctx.drawImage(node,(1920-dw)*(c.x+1)/2,(1080-dh)*(c.y+1)/2,dw,dh);
 }
 return {frame:m.frame,ready};
}
function presentEffects(t){
 const tr=transitionAt(t),alpha=fadeAlpha(t),ctx=transitionContext,c=currentClip(t),p=tr?Math.max(0,Math.min(1,(t-tr.start)/(tr.end-tr.start))):0;
 const layers=tr?[[tr.left,tr.type==='dissolve'?1:Math.max(0,1-2*p)],[tr.right,tr.type==='dissolve'?p:Math.max(0,2*p-1)]]:c?[[c,1]]:[];
 const frames=layers.map(([clip,opacity])=>({...clipFrame(clip),opacity})),missing=frames.some(x=>x.opacity*alpha>.00001&&!x.frame),busy=frames.some(x=>!x.ready);
 transitionCanvas.setAttribute('aria-busy',String(busy));transitionCanvas.dataset.type=tr?tr.type:'end-fade';if(tr)transitionCanvas.dataset.phase=p.toFixed(5);else delete transitionCanvas.dataset.phase;transitionCanvas.dataset.fadeAlpha=alpha.toFixed(5);
 if(!missing){
  ctx.globalAlpha=1;ctx.fillStyle='#000';ctx.fillRect(0,0,1920,1080);for(const layer of frames)if(layer.frame){ctx.globalAlpha=layer.opacity;ctx.drawImage(layer.frame,0,0);}ctx.globalAlpha=1-alpha;ctx.fillStyle='#000';ctx.fillRect(0,0,1920,1080);ctx.globalAlpha=1;
  transitionCanvas.hidden=false;ui.player.hidden=true;image.hidden=true;$('#noMedia').hidden=true;
 }
 const buffering=String(busy||missing);if(transitionCanvas.dataset.buffering!==buffering)transitionCanvas.dataset.buffering=buffering;return !missing;
}
function renderEffects(t,force=false){const tr=transitionAt(t),clips=tr?[tr.left,tr.right]:[currentClip(t)].filter(Boolean);for(const c of clips)positionTransition(c,t,force);return presentEffects(t);}
function sync(force=false){
 if(!active())return;const t=Math.floor((clock()+.000001)*comp().fps)/comp().fps,c=currentClip(t),a=c&&comp().assets.find(a=>a.id===c.asset),player=ui.player;player.muted=true;
 const tr=transitionAt(t),effect=!!tr||fadeAlpha(t)<1;if(!effect)transitionCanvas.hidden=true;if(effect){if(!player.paused)player.pause();renderEffects(t,force);}else{for(const m of transitionMedia.values())if(m.node.tagName==='VIDEO'&&!m.node.paused)m.node.pause();
 if(a){image.hidden=a.kind!=='image';player.hidden=a.kind==='image';const key=a.id+':'+!!a.proxy;if(loaded!==key){loaded=key;if(a.kind==='image'){player.pause();player.removeAttribute('src');image.src=mediaURL(a);image.hidden=false;player.hidden=true;}else{image.hidden=true;player.hidden=false;player.src=mediaURL(a,a.proxy?'proxy':'original');}}
  $('#noMedia').hidden=true;const target=a.kind==='image'?image:player;target.style.objectFit=c.fit;target.style.objectPosition=`${(c.x+1)*50}% ${(c.y+1)*50}%`;
  if(a.kind==='video'){const desired=c.in+t-c.start;if(player.readyState>=1&&(Math.abs(player.currentTime-desired)>(force?.025:.12)))player.currentTime=desired;if(playing&&player.paused)player.play().catch(()=>{});if(!playing)player.pause();}
 }else{loaded='';player.pause();player.hidden=true;image.hidden=true;$('#noMedia').hidden=false;$('#noMedia').textContent='此区间没有画面 · 导出前可用图片补齐';}
 }
 preloadTransition(t);if(comp().fades?.out&&t>comp().duration-comp().fades.out-2){const c=currentClip(Math.min(comp().duration-1/comp().fps,t));if(c)transitionNode(c);}
 if($('#listen').value==='original'){ui.cover.pause();window.CWVideoMonitor?.sync(clock(),playing,force);return;}window.CWVideoMonitor?.pause();
 const audioTime=clock()-state().doc.audioOffset;ui.setMixGain(10**(state().doc.gainDb/20)*Number($('#volume').value));
 if(audioTime>=0&&audioTime<(ui.cover.duration||Infinity)){if(ui.cover.readyState>=1&&(force||Math.abs(ui.cover.currentTime-audioTime)>.12))ui.cover.currentTime=audioTime;if(playing&&ui.cover.paused)ui.cover.play().catch(()=>{});if(!playing)ui.cover.pause();}else ui.cover.pause();
}
function tick(){if(!active()||!playing)return;const t=clock(),a=Number($('#in').value),b=Number($('#out').value);if($('#loop').checked&&b>a&&t>=b)seek(a);else if(t>=comp().duration){pause();position=comp().duration;}
 sync();paintHead();ui.redraw();animation=playing?requestAnimationFrame(tick):null;}
function paintHead(){if(!comp())return;const t=clock(),d=comp().duration;$('#position').textContent=ui.fmt(t);$('#duration').textContent=ui.fmt(d);$('#seek').max=d;$('#seek').value=t;const head=$('#editPlayhead');if(head){head.style.left=t/d*100+'%';const scroll=$('#editScroll'),x=t/d*$('#editCanvas').clientWidth;if(playing&&$('#editFollow').checked&&(x>scroll.scrollLeft+scroll.clientWidth*.88||x<scroll.scrollLeft))scroll.scrollLeft=Math.max(0,x-scroll.clientWidth*.18);}}
function load(doc){if(!doc.composition)return;if(projectId!==doc.id){pause();transitionMedia.clear();projectId=doc.id;position=0;selected=null;library=[];lastImported=[];renderLibrary();}loaded='';position=Math.min(position,doc.composition.duration);ui.player.hidden=false;sync(true);paintHead();}
function gaps(track=null){let end=0,rows=[];for(const c of (track?trackRows(track):pictureEdits.visible(comp())).sort((a,b)=>a.start-b.start)){if(c.start>end+.5/comp().fps)rows.push([end,c.start]);end=Math.max(end,c.start+c.duration);}if(end<comp().duration-.5/comp().fps)rows.push([end,comp().duration]);return rows;}
function selectedClip(){return comp()?.clips.find(c=>c.id===selected);}
function assetFor(c){return comp().assets.find(a=>a.id===c.asset);}
function round(t){return Math.round(t*comp().fps)/comp().fps;}
function normalizeTransitions(){let adjusted=false;const rows=comp().clips;for(let i=0;i<rows.length;i++){const c=rows[i],tr=c.transition,left=trackRows(trackOf(c)).filter(row=>row.start<c.start).at(-1);if(!tr)continue;const max=left?Math.floor(Math.min(10,left.duration,c.duration)*comp().fps/2)*2/comp().fps:0;if(!left||tr.from!==left.id||Math.abs(c.start-left.start-left.duration)>.5/comp().fps||max<2/comp().fps){delete c.transition;adjusted=true;}else{const duration=Math.min(max,Math.max(2/comp().fps,Math.round(tr.duration*comp().fps/2)*2/comp().fps));if(Math.abs(tr.duration-duration)>.000001){tr.duration=duration;adjusted=true;}}}if(adjusted)ui.message('片段边界已改变，相关转场已缩短或移除；音乐与字幕保持原位');}
function normalizeFades(){if(!comp().fades)return;const f=comp().fades,fps=comp().fps,total=Math.round(comp().duration*fps);let remaining=total;for(const key of ['in','out']){let n=Math.min(remaining,10*fps,Math.round((f[key]||0)*fps));if(n<2)n=0;f[key]=n/fps;remaining-=n;}if(!f.in&&!f.out)delete comp().fades;}
function commit(label){comp().clips.sort((a,b)=>a.start-b.start);normalizeTransitions();normalizeFades();ui.mark({label});render();sync(true);}
function assertClips(clips){pictureEdits.checked({...comp(),clips:[...clips]});}
function addAsset(a){if(!comp().assets.some(x=>x.id===a.id))comp().assets.push(structuredClone(a));}
function append(a,fill=false){pause();if(a.kind==='audio'){ui.cover.pause();$('#audio').value=a.path;$('#audio').dispatchEvent(new Event('input'));ui.message('已选择为混音，请保存后使用“混音时长”设置成片长度');return;}addAsset(a);
 const spaces=fill?gaps(selectedTrack):[[Math.max(0,...trackRows().map(c=>c.start+c.duration)),Infinity]];if(fill&&a.kind!=='image')return;
 for(const [start,end] of spaces){const length=fill?end-start:a.kind==='image'?5:Math.max(1/comp().fps,Math.floor(a.duration*comp().fps)/comp().fps);const c={id:'C'+crypto.randomUUID().replaceAll('-',''),asset:a.id,start:round(start),in:0,duration:round(length),fit:'contain',x:0,y:0,...(comp().tracks?{track:selectedTrack}:{})};comp().duration=Math.max(comp().duration,c.start+c.duration);comp().clips.push(c);selected=c.id;}
 commit(fill?'用图片补齐画面空白':'添加画面片段');}
function renderLibrary(){const query=$('#editSearch').value.toLowerCase();$('#editMedia').innerHTML=library.filter(a=>a.name.toLowerCase().includes(query)).map(a=>`<article class="media-card"><button class="media-preview" data-media-preview="${a.id}" ${a.kind!=='audio'?`draggable="true" data-media-drag="${a.id}"`:""} title="${a.kind==='audio'?'预览素材':'点击预览 · 拖到画面轨放置'}">${a.thumbnail?`<img src="${mediaURL(a,'thumb')}" alt="" draggable="false">`:`<span>${a.kind==='audio'?'♫':'▷'}</span>`}<small>${a.kind==='image'?'图片':ui.fmt(a.duration)}</small></button><strong title="${esc(a.name)}">${esc(a.name)}</strong><span>${a.width?a.width+' × '+a.height:'音频'}${a.proxy?' · 已有代理':''}</span><div><button class="quiet" data-media-add="${a.id}">${a.kind==='audio'?'设为混音':'＋ 加到末尾'}</button>${a.kind!=='audio'?`<button class="quiet" data-media-insert="${a.id}">插到播放头</button>`:''}${a.kind==='video'?`<button class="quiet" data-media-full="${a.id}" title="从 0 秒使用整段剪辑，保留音乐与字幕">整段替换画面</button>`:''}${a.kind==='image'?`<button class="quiet" data-media-fill="${a.id}">补齐空白</button>`:a.kind==='video'?`<button class="quiet" data-media-proxy="${a.id}">网页代理</button>`:''}</div><button class="media-relink quiet" data-media-relink="${a.id}">重新定位 / 替换引用</button></article>`).join('')||'<div class="media-empty">把这一首歌的画面，收在这里。<small>支持视频、图片和混音；链接下载完成后也可加入。</small></div>';
 $$('[data-media-full]').forEach(b=>b.onclick=ui.safe(()=>useFullVideo(library.find(a=>a.id===b.dataset.mediaFull))));
 $$('[data-media-insert]').forEach(b=>b.onclick=ui.safe(()=>insertAtHead(library.find(a=>a.id===b.dataset.mediaInsert))));
 $$('[data-media-add]').forEach(b=>b.onclick=ui.safe(()=>addToPicture(library.find(a=>a.id===b.dataset.mediaAdd))));$$('[data-media-fill]').forEach(b=>b.onclick=ui.safe(()=>addToPicture(library.find(a=>a.id===b.dataset.mediaFill),true)));
 $$('[data-media-proxy]').forEach(b=>b.onclick=ui.safe(async()=>{const id=projectId;b.disabled=true;$('#editLibraryStatus').textContent='正在生成本机网页代理，请稍候；不会更改原素材。';try{const a=await ui.api('/api/video-media-proxy/'+id,{asset:b.dataset.mediaProxy}).catch(e=>{if(projectId===id)$('#editLibraryStatus').textContent='代理生成失败：'+e.message;throw e;});if(id!==projectId)return;library=library.map(x=>x.id===a.id?a:x);if(comp()){comp().assets=comp().assets.map(x=>x.id===a.id?a:x);loaded='';commit('选择网页代理');}renderLibrary();$('#editLibraryStatus').textContent='网页代理已就绪；导出仍使用原素材';}finally{b.disabled=false;}}));
 $$('[data-media-relink]').forEach(b=>b.hidden=!comp());$$('[data-media-relink]').forEach(b=>b.onclick=ui.safe(()=>ui.pick('video-media',async path=>{const id=projectId,old=library.find(a=>a.id===b.dataset.mediaRelink);try{const a=await ui.api('/api/video-media-import/'+id,{path});if(id!==projectId)return;if(a.kind!==old.kind)throw Error('替换素材应与原素材类型相同');if(comp().clips.some(c=>c.asset===old.id&&a.kind==='video'&&c.in+c.duration>a.duration))throw Error('替换素材太短，无法保留现有修剪区间');addAsset(a);for(const c of comp().clips)if(c.asset===old.id)c.asset=a.id;library=await ui.api('/api/video-library/'+id);commit('重新定位画面素材');renderLibrary();}catch(e){ui.message(e.message);}},'')));
 $$('[data-media-preview]').forEach(b=>b.onclick=()=>{pause();const a=library.find(a=>a.id===b.dataset.mediaPreview);$('#editMediaPreviewTitle').textContent=a.name;$('#editMediaPreviewBody').innerHTML=a.kind==='image'?`<img src="${mediaURL(a)}" alt="素材预览">`:`<${a.kind==='audio'?'audio':'video'} src="${mediaURL(a,a.proxy?'proxy':'original')}" controls preload="metadata"></${a.kind==='audio'?'audio':'video'}>`;mediaDialog.showModal();});
}
$('#editMediaPreviewClose').onclick=()=>mediaDialog.close();mediaDialog.addEventListener('close',()=>{$('#editMediaPreviewBody').replaceChildren();});
async function importPaths(paths){if(importBusy)return;const id=projectId,files=[...new Set(Array.isArray(paths)?paths:[paths])];importBusy=true;importStop=false;lastImported=[];$('#editImportCancel').disabled=false;importControls();const failures=[];let finished=0;
 try{for(const path of files){if(importStop||closed||projectId!==id)break;$('#editLibraryStatus').textContent='导入 '+(finished+1)+' / '+files.length+'：'+path.split(/[\\/]/).pop();try{const a=await ui.api('/api/video-media-import/'+encodeURIComponent(id),{path});if(projectId!==id)break;if(!lastImported.some(x=>x.id===a.id))lastImported.push(a);}catch(e){failures.push(path.split(/[\\/]/).pop()+'：'+e.message);}finished++;}if(projectId!==id)return;library=await ui.api('/api/video-library/'+encodeURIComponent(id));renderLibrary();$('#editLibraryStatus').textContent='已处理 '+finished+' / '+files.length+' 项，媒体库收录 '+lastImported.length+' 项'+(importStop?'（已停止后续）':'')+(failures.length?'；失败 '+failures.length+' 项：'+failures.join('；'):'')+'。导入不会移动现有画面或字幕。';
 }finally{importBusy=false;importControls();}
}
async function importPath(path){return importPaths([path]);}
$('#editImport').onclick=ui.safe(()=>ui.pick('video-media',importPaths,'',{multiple:true}));$('#editSearch').oninput=renderLibrary;
$('#editRefresh').onclick=ui.safe(async()=>{const id=projectId;const rows=await ui.api('/api/video-library/'+id);if(id===projectId){library=rows;renderLibrary();}});
function inspector(){const c=selectedClip();$('#editInspector').innerHTML=c?`<h3>当前片段 · ${esc(assetFor(c).name)}</h3><div class="pair"><label>视频轨<select data-clip-track>${trackList().map(t=>`<option value="${t.id}" ${t.id===trackOf(c)?'selected':''}>${esc(t.name)}</option>`).join('')}</select></label>${[['start','成片位置'],['in','素材入点'],['duration','持续时长'],['out','素材出点']].map(([k,l])=>`<label>${l} · 秒<input data-clip-field="${k}" type="number" step="0.04" min="0" value="${(k==='out'?c.in+c.duration:c[k]).toFixed(3)}"></label>`).join('')}<label>画面适配<select data-clip-field="fit"><option value="contain" ${c.fit==='contain'?'selected':''}>完整显示 · 黑边</option><option value="cover" ${c.fit==='cover'?'selected':''}>裁切填满</option></select></label><label>水平取景<input data-clip-field="x" type="range" min="-1" max="1" step="0.05" value="${c.x}"></label><label>垂直取景<input data-clip-field="y" type="range" min="-1" max="1" step="0.05" value="${c.y}"></label></div><p class="hint">入点与时长只修剪当前片段，音乐和字幕保持原位。</p>`:'<p class="hint">点击时间轴片段，在这里精确调整入点、时长和取景。</p>';
 if(c)$('[data-clip-track]').onchange=ui.safe(e=>{const plan=structuredClone(comp()),row=plan.clips.find(x=>x.id===c.id);row.track=e.target.value;delete row.transition;applyPlan(plan,c.id,'移动到视频轨');selectedTrack=row.track;});
 $$('[data-clip-field]').forEach(input=>input.onchange=()=>{const old=structuredClone(c),key=input.dataset.clipField;if(key==='out')c.duration=round(Number(input.value)-c.in);else c[key]=key==='fit'?input.value:['start','duration'].includes(key)?round(Number(input.value)):Number(input.value);try{assertClips(comp().clips);commit('调整画面片段');}catch(e){Object.assign(c,old);inspector();ui.message(e.message);}});
}
function renderTransitions(){const rows=trackRows(selectedClip()?trackOf(selectedClip()):selectedTrack),choices=rows.slice(1).filter((r,i)=>Math.abs(r.start-rows[i].start-rows[i].duration)<.5/comp().fps);let id=transitionEditor.dataset.clip;if(!choices.some(c=>c.id===id))id=choices.find(c=>c.id===selected)?.id||choices[0]?.id;transitionEditor.dataset.clip=id||'';const right=choices.find(c=>c.id===id),index=rows.indexOf(right),left=rows[index-1],max=left?Math.floor(Math.min(10,left.duration,right.duration)*comp().fps/2)*2/comp().fps:0,tr=right?.transition;
 transitionEditor.innerHTML=`<div><span class="eyebrow">PICTURE TRANSITION</span><strong>接点转场</strong></div>${right?`<label>片段接点<select id="editTransitionBoundary">${choices.map(c=>`<option value="${c.id}" ${c.id===id?'selected':''}>${ui.fmt(c.start)} · ${esc(assetFor(rows[rows.indexOf(c)-1]).name)} → ${esc(assetFor(c).name)}</option>`).join('')}</select></label><label>转场<select id="editTransitionType"><option value="none">直接切换</option><option value="dissolve" ${tr?.type==='dissolve'?'selected':''}>交叉溶解</option><option value="fade" ${tr?.type==='fade'?'selected':''}>淡出至黑 · 再淡入</option></select></label><label>时长 · 秒<input id="editTransitionDuration" type="number" min="${2/comp().fps}" max="${max}" step="${2/comp().fps}" value="${(tr?.duration||Math.min(1,max)).toFixed(3)}" ${!tr?'disabled':''}></label><button id="editTransitionPreview" class="quiet">试听此接点</button>`:'<p class="hint">把两个片段接在一起后，可在接点添加转场。</p>'}<p class="hint transition-explanation">色带两端可拖动，实时预览；Esc 取消，方向键微调。以接点为中心，向两侧各展开一半；修剪范围外用首尾帧补足。不会缩短成片或移动音乐与字幕。</p>`;
 if(!right)return;$('#editTransitionBoundary').onchange=e=>{transitionEditor.dataset.clip=e.target.value;renderTransitions();};const change=()=>{const type=$('#editTransitionType').value,value=Number($('#editTransitionDuration').value),frames=Math.round(value*comp().fps/2)*2;if(type!=='none'&&(!Number.isFinite(value)||frames<2||frames/comp().fps>max+.001)){ui.message('转场时长应在 '+(2/comp().fps).toFixed(3)+'–'+max.toFixed(3)+' 秒之间');renderTransitions();return;}pause();if(type==='none')delete right.transition;else right.transition={type,duration:frames/comp().fps,from:left.id};commit('调整画面转场');};$('#editTransitionType').onchange=change;$('#editTransitionDuration').onchange=change;$('#editTransitionPreview').onclick=ui.safe(async()=>{const d=right.transition?.duration||Math.min(1,max);pause();$('#in').value=Math.max(0,right.start-d/2-.5).toFixed(3);$('#out').value=Math.min(comp().duration,right.start+d/2+.5).toFixed(3);seek(Number($('#in').value));if(state().doc.audio)await toggle();});
}
function fadeLimit(key){const fps=comp().fps,other=key==='in'?'out':'in';return Math.max(0,Math.min(10,Math.round(comp().duration*fps)/fps-(comp().fades?.[other]||0)));}
function effectHandles(id,kind,edges,duration){return edges.map(edge=>`<button type="button" class="effect-handle ${edge}" data-effect-kind="${kind}" data-effect-id="${id}" data-effect-edge="${edge}" aria-label="${kind==='transition'?'转场':id==='in'?'片头淡入':'片尾淡出'}${edge==='left'?'左':'右'}端 · 拖动调整时长" title="拖动调整时长 · 方向键微调">Ⅱ</button>`).join('');}
function renderFades(){
 $$('[data-end-fade]').forEach(el=>el.remove());
 const f=comp().fades||{},fps=comp().fps;
 fadeEditor.innerHTML=`<div class="end-fade-title"><span class="eyebrow">OPENING & CLOSING</span><strong>片头 / 片尾</strong></div>${['in','out'].map(key=>`<div class="end-fade-control"><label class="check"><input type="checkbox" data-fade-enable="${key}" ${f[key]?'checked':''}>${key==='in'?'片头淡入':'片尾淡出'}</label><label>时长 · 秒<input type="number" data-fade-duration="${key}" min="${2/fps}" max="${fadeLimit(key)}" step="${1/fps}" value="${(f[key]||Math.min(1,fadeLimit(key))).toFixed(3)}" ${!f[key]?'disabled':''}></label></div>`).join('')}<p class="hint">仅淡化画面；不改变音乐音量、字幕显示或任何时间。拖动色带的活动端可实时预览，Esc 取消，松手后可撤销。</p>`;
 for(const key of ['in','out']){
  const enabled=$(`[data-fade-enable="${key}"]`),input=$(`[data-fade-duration="${key}"]`);
  const change=()=>{pause();const n=enabled.checked?Math.round(Number(input.value)*fps):0,max=Math.round(fadeLimit(key)*fps);if(!Number.isFinite(n)||n<0||n>max||(enabled.checked&&n<2)){ui.message('淡化时长应在 '+(2/fps).toFixed(3)+'–'+(max/fps).toFixed(3)+' 秒之间');renderFades();return;}comp().fades??={in:0,out:0};comp().fades[key]=n/fps;commit('调整片头片尾画面淡化');};
  enabled.onchange=change;input.onchange=change;
 }
 for(const key of ['in','out'])if(f[key]){const start=key==='in'?0:comp().duration-f[key];$('#editCanvas').insertAdjacentHTML('beforeend',`<div class="end-fade-marker ${key}" data-end-fade="${key}" style="top:${26+trackList().length*108+5}px;left:${start/comp().duration*100}%;width:${f[key]/comp().duration*100}%"><button class="effect-label" type="button">${key==='in'?'◔ 淡入':'◕ 淡出'} <span data-effect-value>${f[key].toFixed(2)}s</span></button>${effectHandles(key,'end',[key==='in'?'right':'left'],f[key])}</div>`);}
 $$('[data-end-fade]').forEach(marker=>marker.querySelector('.effect-label').onclick=()=>{const key=marker.dataset.endFade;seek(key==='in'?comp().fades.in/2:comp().duration-comp().fades.out/2);$(`[data-fade-duration="${key}"]`).focus();});
}
function effectInfo(kind,id){
 if(kind==='end'){const duration=comp().fades?.[id]||0;return {duration,max:fadeLimit(id),start:id==='in'?0:comp().duration-duration};}
 const tr=transitionRows().find(tr=>tr.right.id===id);return tr?{...tr,max:Math.floor(Math.min(10,tr.left.duration,tr.right.duration)*comp().fps/2)*2/comp().fps}:null;
}
function setEffectDuration(kind,id,value){if(kind==='end')comp().fades[id]=value;else comp().clips.find(c=>c.id===id).transition.duration=value;}
function startEffectDrag(e,handle){
 const kind=handle.dataset.effectKind,id=handle.dataset.effectId,info=effectInfo(kind,id);if(!info?.duration)return;
 pause();const originalPosition=clock(),probe=originalPosition>=info.start&&originalPosition<info.start+info.duration?originalPosition:info.start+info.duration*(kind==='transition'?.25:.5);
 effectDrag={kind,id,info,edge:handle.dataset.effectEdge,x:e.clientX,width:$('#editCanvas').clientWidth,handle,pointer:e.pointerId,originalPosition,probe};
 if(kind==='transition')transitionEditor.dataset.clip=id;
 ui.history.begin('拖动'+(kind==='transition'?'画面转场':id==='in'?'片头淡入':'片尾淡出'));
 handle.setPointerCapture(e.pointerId);handle.closest('.transition-marker,.end-fade-marker').classList.add('is-dragging');seek(probe);e.preventDefault();e.stopPropagation();
}
function moveEffectDrag(e){
 const d=effectDrag;if(!d)return;const fps=comp().fps,delta=(e.clientX-d.x)/d.width*comp().duration,sign=d.edge==='left'?-1:1,step=d.kind==='transition'?2:1;
 let frames=Math.round((d.info.duration+delta*sign*(d.kind==='transition'?2:1))*fps/step)*step;frames=Math.max(2,Math.min(Math.floor(d.info.max*fps/step)*step,frames));
 const duration=frames/fps;setEffectDuration(d.kind,d.id,duration);const start=d.kind==='transition'?d.info.right.start-duration/2:d.id==='in'?0:comp().duration-duration,marker=d.handle.closest('.transition-marker,.end-fade-marker');
 marker.style.left=start/comp().duration*100+'%';marker.style.width=duration/comp().duration*100+'%';marker.querySelector('[data-effect-value]').textContent=duration.toFixed(2)+'s';
 const input=d.kind==='transition'?$('#editTransitionDuration'):$(`[data-fade-duration="${d.id}"]`);if(input)input.value=duration.toFixed(3);
 ui.mark({label:'调整画面效果时长'});seek(d.probe);effectStatus.textContent=`${d.kind==='transition'?'转场':d.id==='in'?'片头淡入':'片尾淡出'} ${duration.toFixed(3)} 秒 · 固定时间预览 ${ui.fmt(d.probe)} · 松手确认，Esc 取消`;e.preventDefault();
}
function finishEffectDrag(cancel=false){
 const d=effectDrag;if(!d)return;if(cancel)setEffectDuration(d.kind,d.id,d.info.duration);
 ui.mark({label:'调整画面效果时长'});ui.history.end();effectDrag=null;if(d.handle.hasPointerCapture(d.pointer))d.handle.releasePointerCapture(d.pointer);
 render();seek(cancel?d.originalPosition:d.probe);effectStatus.textContent=cancel?'已取消拖动；画面效果已恢复。':'已调整画面效果；Ctrl+Z 可撤销。音乐与字幕时间保持不变。';
}
$('#editCanvas').addEventListener('pointerdown',e=>{const handle=e.target.closest('[data-effect-edge]');if(e.button===0&&active()&&handle)startEffectDrag(e,handle);});
$('#editCanvas').addEventListener('pointermove',moveEffectDrag);
$('#editCanvas').addEventListener('pointerup',()=>finishEffectDrag());
$('#editCanvas').addEventListener('pointercancel',()=>finishEffectDrag(true));
$('#editCanvas').addEventListener('lostpointercapture',()=>finishEffectDrag(true));
$('#editCanvas').addEventListener('keydown',e=>{const h=e.target.closest('[data-effect-edge]');if(!h||!['ArrowLeft','ArrowRight'].includes(e.key))return;e.preventDefault();e.stopPropagation();pause();const kind=h.dataset.effectKind,id=h.dataset.effectId,info=effectInfo(kind,id),step=(kind==='transition'?2:1)*(e.shiftKey?5:1)/comp().fps,sign=(e.key==='ArrowRight'?1:-1)*(h.dataset.effectEdge==='left'?-1:1);setEffectDuration(kind,id,Math.max(2/comp().fps,Math.min(info.max,round(info.duration+step*sign))));commit('微调画面效果时长');$(`[data-effect-kind="${kind}"][data-effect-id="${id}"][data-effect-edge="${h.dataset.effectEdge}"]`)?.focus({preventScroll:true});});
window.addEventListener('keydown',e=>{if(!effectDrag)return;if(e.key==='Escape'){e.preventDefault();e.stopImmediatePropagation();finishEffectDrag(true);}else if((e.ctrlKey||e.metaKey)&&['z','y'].includes(e.key.toLowerCase()))finishEffectDrag();},true);
window.addEventListener('blur',()=>finishEffectDrag(true));
window.addEventListener('cw-video-history-before',()=>finishEffectDrag());
function trackTop(id){return 50+[...trackList()].reverse().findIndex(t=>t.id===id)*108;}
function trackAt(y){const row=$$('.picture-lane[data-track]').find(el=>{const b=el.getBoundingClientRect();return y>=b.top&&y<=b.bottom;});return row?.dataset.track||selectedTrack;}
function trackMarkup(c){return [...trackList()].reverse().map(t=>`<section class="picture-track ${t.hidden?'track-muted':''}" data-track-section="${t.id}"><div class="picture-track-head" data-track="${t.id}"><div class="picture-track-actions"><button type="button" class="quiet track-pick ${t.id===selectedTrack?'active':''}" data-track-action="select" data-track="${t.id}">${esc(t.name)}</button><button type="button" class="quiet" data-track-action="hide" data-track="${t.id}" title="显示状态同时用于预览和导出" aria-label="${t.hidden?'显示':'隐藏'} ${esc(t.name)}" aria-pressed="${!t.hidden}">${t.hidden?'○ 已隐藏':'◉ 可见'}</button><button type="button" class="quiet" data-track-action="up" data-track="${t.id}" title="提高覆盖层级">↑</button><button type="button" class="quiet" data-track-action="down" data-track="${t.id}" title="降低覆盖层级">↓</button><button type="button" class="quiet" data-track-action="rename" data-track="${t.id}">改名</button><button type="button" class="quiet" data-track-action="remove" data-track="${t.id}" ${trackList().length===1||trackRows(t.id).length?'disabled':''}>移除空轨</button></div></div><div class="picture-lane" data-track="${t.id}" aria-label="${esc(t.name)} 画面轨">${trackRows(t.id).map(clip=>`<div class="picture-clip ${selected===clip.id?'selected':''}" data-picture="${clip.id}" tabindex="0" role="button" aria-label="${esc(assetFor(clip).name)} ${ui.fmt(clip.start)}" style="left:${clip.start/c.duration*100}%;width:${clip.duration/c.duration*100}%"><div class="clip-filmstrip" aria-hidden="true"></div><span class="trim-edge" data-edge="left"></span><span class="picture-clip-name">${esc(assetFor(clip).name)}</span><small>${ui.fmt(clip.duration)}</small><span class="trim-edge" data-edge="right"></span></div>`).join('')}</div></section>`).join('');}
function editTracks(fn,label){pause();const plan=structuredClone(comp());plan.tracks=structuredClone(trackList());fn(plan);applyPlan(plan,selected,label);}
function bindTrackControls(){
 $$('[data-track-action]').forEach(b=>b.onclick=ui.safe(async()=>{const id=b.dataset.track,action=b.dataset.trackAction;
  if(action==='select'){selectedTrack=id;selected=null;render();return;}
  if(action==='rename'){const t=trackList().find(t=>t.id===id);await ui.promptForm('轨道名称','<label>名称<input id="pictureTrackName" maxlength="60" value="'+esc(t.name)+'"></label>',()=>{const name=$('#pictureTrackName').value.trim();if(!name)throw Error('请输入轨道名称');editTracks(p=>p.tracks.find(t=>t.id===id).name=name,'修改画面轨道名');});return;}
  editTracks(p=>{const t=p.tracks.find(t=>t.id===id),index=p.tracks.indexOf(t);if(action==='hide')t.hidden=!t.hidden;
   if(action==='up'||action==='down'){const other=index+(action==='up'?1:-1);if(other>=0&&other<p.tracks.length)[p.tracks[index],p.tracks[other]]=[p.tracks[other],p.tracks[index]];}
   if(action==='remove'&&p.tracks.length>1&&!p.clips.some(c=>trackOf(c)===id))p.tracks=p.tracks.filter(t=>t.id!==id);
  },action==='hide'?'显示或隐藏视频轨':'调整视频轨层级');
 }));
}
$('#editTargetTrack').onchange=e=>{selectedTrack=e.target.value;selected=null;render();};
$('#editAddTrack').onclick=ui.safe(async()=>{await ensureEdit();if(!comp())return;if(trackList().length>=8)throw Error('最多支持 8 条画面轨');const ids=new Set(trackList().map(t=>t.id));let number=1;while(ids.has('V'+number))number++;const id='V'+number;selectedTrack=id;selected=null;editTracks(p=>p.tracks.push({id,name:'视频 '+number,hidden:false}),'添加视频轨');ui.message('新轨在上层，覆盖下层画面；可拖素材或片段到这一轨');});

function render(){if(effectDrag||drag)return;for(const b of $$('[data-edit-history]'))b.disabled=!ui.history.status()[b.dataset.editHistory];const c=comp();panel.hidden=!state().doc;timeline.hidden=!c;$('#editModeTitle').textContent=c?'多素材剪辑已启用':'可以先导入多个视频，再开始剪辑';$('#editModeNote').textContent=c?'拖动缩略图到画面轨，或插到播放头；导入本身不改变时间轴。':'启用后保留原视频为第一段，混音、字幕和对齐沿用当前工程。';$('#editEnable').hidden=!!c;importControls();welcome.querySelector('p').textContent=c?'当前为独立画面剪辑。原文、译文与混音在固定的成片时间线上。':'用 OP、ED、PV、图片和自己的视频拼出画面。音乐与字幕独立保留。';$('#editCopy').disabled=!state().doc;document.body.classList.toggle('edit-mode',!!c);$('#raw').textContent=c?'回到剪辑时间轴':'回到原视频时间轴';$('#analyze').disabled=!!c;$('#listen').disabled=!!state().exact;if(!c){transitionCanvas.hidden=true;image.hidden=true;ui.player.hidden=false;ui.player.style.objectFit='contain';ui.player.style.objectPosition='50% 50%';return;}
 position=Math.min(position,c.duration);if(Number($('#out').value)>c.duration)$('#out').value=c.duration.toFixed(3);if(Number($('#in').value)>=c.duration)$('#in').value=0;$('#editDuration').value=c.duration.toFixed(3);$('#editFps').value=c.fps;$('#editAllowGaps').checked=c.allowGaps;$('#listen').disabled=!!state().exact;$('#analyze').disabled=true;
 if(!trackList().some(t=>t.id===selectedTrack))selectedTrack=trackList()[0].id;$('#editTargetTrack').innerHTML=trackList().map(t=>`<option value="${t.id}" ${t.id===selectedTrack?'selected':''}>${esc(t.name)}${t.hidden?' · 已隐藏':''}</option>`).join('');$('#editAddTrack').disabled=trackList().length>=8;
 const mixLength=Number.isFinite(ui.cover.duration)?ui.cover.duration:c.duration,mixStart=Math.max(0,state().doc.audioOffset),mixEnd=Math.max(mixStart,Math.min(c.duration,mixLength+state().doc.audioOffset));const canvas=$('#editCanvas'),width=Math.max(1,$('#editScroll').clientWidth)*zoom;canvas.style.width=width+'px';const tick=[1,2,5,10,15,30,60,120,300,600].find(n=>n/c.duration*width>=65)||600;let ruler='';for(let t=0;t<c.duration;t+=tick)ruler+=`<span style="left:${t/c.duration*100}%">${ui.fmt(t).slice(0,-4)}</span>`;
 canvas.innerHTML=`<div class="picture-ruler">${ruler}</div>${trackMarkup(c)}<div class="picture-effect-lanes" aria-hidden="true"><span>接点转场</span><span>片头 / 片尾</span></div><div class="music-lane"><span class="lane-label">混音</span><span class="music-clip" style="left:${mixStart/c.duration*100}%;width:${Math.max(0,mixEnd-mixStart)/c.duration*100}%">♫ ${esc(state().doc.audio?.split(/[\\/]/).pop()||'请导入最终混音')} · 独立音轨</span></div><div class="edit-playhead" id="editPlayhead"></div>`;
 const spaces=gaps();$('#editCoverage').textContent=spaces.length?`${spaces.length} 处画面空白 · 共 ${spaces.reduce((n,[a,b])=>n+b-a,0).toFixed(2)} 秒${c.allowGaps?' · 将输出黑底':' · 可导入图片并点“补齐空白”'}`:`✓ 画面覆盖完整 · ${c.clips.length} 个片段 · ${ui.fmt(c.duration)}`;$('#editCoverage').classList.toggle('has-gaps',!!spaces.length);
 const marks=transitionRows().map(tr=>`<div class="transition-marker ${tr.type}" data-transition="${tr.right.id}" aria-label="${tr.type==='dissolve'?'交叉溶解':'淡出淡入'} ${tr.duration.toFixed(2)} 秒" title="点击调整转场" style="top:${trackTop(trackOf(tr.right))+63}px;left:${tr.start/c.duration*100}%;width:${tr.duration/c.duration*100}%"><button class="effect-label" type="button">${tr.type==='dissolve'?'◇':'◐'} <span data-effect-value>${tr.duration.toFixed(2)}s</span></button>${effectHandles(tr.right.id,'transition',['left','right'],tr.duration)}</div>`).join('');canvas.insertAdjacentHTML('beforeend',marks);$$('[data-transition]').forEach(b=>b.onclick=()=>{transitionEditor.dataset.clip=b.dataset.transition;renderTransitions();});renderTransitions();renderFades();
 for(const id of ['editSplit','editDuplicate','editDelete','editRipple','editEarlier','editLater'])$('#'+id).disabled=!selectedClip();inspector();paintHead();bindTrackControls();window.dispatchEvent(new Event('cw-picture-render'));
}
$('#editDuration').onchange=()=>{const value=Number($('#editDuration').value),old=comp().duration;if(!Number.isFinite(value)||value<.1||value>21600)return;comp().duration=value;try{assertClips(comp().clips);commit('调整成片时长');}catch(e){comp().duration=old;render();ui.message(e.message);}};
$('#editFps').onchange=()=>{comp().fps=Number($('#editFps').value);commit('调整剪辑帧率');};$('#editAllowGaps').onchange=()=>{comp().allowGaps=$('#editAllowGaps').checked;commit('设置画面空白策略');};
$('#editFitMusic').onclick=ui.safe(async()=>{const id=projectId,info=await ui.api('/api/video-media-info/'+id,{path:state().doc.audio});if(id!==projectId)return;const end=round(Math.max(.1,info.duration+state().doc.audioOffset));if(comp().clips.some(c=>c.start+c.duration>end+.001))throw Error('现有画面超出混音终点，请先修剪末尾片段');comp().duration=end;commit('使用成品混音时长');});
$$('[data-edit-history]').forEach(b=>b.onclick=()=>{pause();ui.history[b.dataset.editHistory]();});
$('#editSplit').onclick=()=>{pause();const c=selectedClip(),at=round(clock());if(!c||at<=c.start||at>=c.start+c.duration){ui.message('把播放头放在选中片段内部再分割');return;}const right={...c,id:'C'+crypto.randomUUID().replaceAll('-',''),start:at,in:c.in+at-c.start,duration:c.start+c.duration-at};delete right.transition;c.duration=at-c.start;comp().clips.push(right);selected=right.id;commit('分割画面片段');};
$('#editDuplicate').onclick=()=>{const c=selectedClip();if(!c)return;const row={...c,id:'C'+crypto.randomUUID().replaceAll('-',''),start:Math.max(...trackRows(trackOf(c)).map(x=>x.start+x.duration))};comp().clips.push(row);comp().duration=Math.max(comp().duration,row.start+row.duration);selected=row.id;commit('复制画面片段');};
function remove(ripple){pause();const c=selectedClip();if(!c)return;comp().clips=comp().clips.filter(x=>x!==c);if(ripple)for(const x of comp().clips)if(trackOf(x)===trackOf(c)&&x.start>=c.start+c.duration-.001)x.start-=c.duration;selected=null;commit(ripple?'移除并接拢画面':'移除画面并留空');}
function reorder(direction){pause();const rows=trackRows(selectedClip()?trackOf(selectedClip()):selectedTrack),i=rows.findIndex(c=>c.id===selected),j=i+direction;if(i<0||j<0||j>=rows.length)return;const a=rows[Math.min(i,j)],b=rows[Math.max(i,j)],gap=b.start-a.start-a.duration,start=a.start;b.start=start;a.start=start+b.duration+gap;commit('调整画面顺序');}
$('#editEarlier').onclick=()=>reorder(-1);$('#editLater').onclick=()=>reorder(1);
$('#editDelete').onclick=()=>remove(false);$('#editRipple').onclick=()=>remove(true);$('#editZoom').oninput=()=>{zoom=Number($('#editZoom').value);render();$('#editScroll').scrollLeft=Math.max(0,clock()/comp().duration*$('#editCanvas').clientWidth-$('#editScroll').clientWidth*.4);};
// Picture-only drag plans remain outside the document until the user drops them.
const mediaMime='application/x-coverworkbench-media';
let mediaDrag=null,scrollFrame=0,scrollPoint=null,scrollUpdate=null;
const newClipId=()=> 'C'+crypto.randomUUID().replaceAll('-','');
function pointerTime(x){const box=$('#editCanvas').getBoundingClientRect();return Math.max(0,Math.min(comp().duration,(x-box.left)/box.width*comp().duration));}
function snappedTime(at,event,exclude,moveLength=0,track=selectedTrack){
 let value=round(at);if(!$('#editSnap').checked||event.altKey)return value;
 const points=[0,clock(),comp().duration,...comp().clips.filter(c=>c.id!==exclude&&trackOf(c)===track).flatMap(c=>[c.start,c.start+c.duration])];
 if(moveLength)points.push(...points.map(t=>t-moveLength));
 const threshold=Math.min(.12,8/$('#editCanvas').clientWidth*comp().duration),nearest=points.sort((a,b)=>Math.abs(a-value)-Math.abs(b-value))[0];
 if(Math.abs(nearest-value)<=threshold)value=round(nearest);return value;
}
function dragMode(){return $('#editDragMode').value;}
function stopScroll(){cancelAnimationFrame(scrollFrame);scrollFrame=0;scrollPoint=null;scrollUpdate=null;}
function autoScroll(event,update){
 scrollPoint={clientX:event.clientX,clientY:event.clientY,altKey:event.altKey};scrollUpdate=update;
 if(scrollFrame)return;
 const step=()=>{scrollFrame=0;if(!scrollPoint||!scrollUpdate)return;const scroller=$('#editScroll'),box=scroller.getBoundingClientRect(),x=scrollPoint.clientX;
  const speed=x<box.left+36?-Math.min(18,(box.left+36-x)/2):x>box.right-36?Math.min(18,(x-box.right+36)/2):0;
  if(speed){const old=scroller.scrollLeft;scroller.scrollLeft+=speed;if(scroller.scrollLeft!==old)scrollUpdate(scrollPoint);}
  scrollFrame=requestAnimationFrame(step);
 };scrollFrame=requestAnimationFrame(step);
}
function clearDrop(){
 $('#editDropGhost')?.remove();$('#editDropLine')?.remove();$('#editDropLabel')?.remove();$$('.picture-drop-shifted').forEach(el=>el.remove());
 $('#editScroll').classList.remove('picture-drop-active','picture-drop-invalid');
 for(const el of $$('[data-picture]')){const row=comp()?.clips.find(c=>c.id===el.dataset.picture);if(row){el.style.left=row.start/comp().duration*100+'%';el.style.width=row.duration/comp().duration*100+'%';}el.style.transform='';el.classList.remove('picture-moving');}
 $('#editPictureDragStatus').textContent='';
}
const dragStatus=document.createElement('p');dragStatus.id='editPictureDragStatus';dragStatus.className='hint picture-drag-status';dragStatus.setAttribute('role','status');$('#editCoverage').after(dragStatus);
function paintDrop(plan,clipId,at,length,note,error=''){
 clearDrop();const canvas=$('#editCanvas'),duration=comp().duration;
 if(plan)for(const el of $$('[data-picture]')){const row=plan.clips.find(c=>c.id===el.dataset.picture);if(row){el.style.left=row.start/duration*100+'%';el.style.width=row.duration/duration*100+'%';el.style.transform=`translateY(${trackTop(trackOf(row))-trackTop(trackOf(comp().clips.find(c=>c.id===row.id)))}px)`;}if(el.dataset.picture===clipId)el.classList.add('picture-moving');}
 if(plan)for(const row of plan.clips.filter(c=>c.id!==clipId&&!comp().clips.some(old=>old.id===c.id))){const part=document.createElement('div');part.className='picture-drop-shifted';part.style.top=(trackTop(trackOf(row))+6)+'px';part.style.left=row.start/duration*100+'%';part.style.width=row.duration/duration*100+'%';part.textContent=plan.assets.find(a=>a.id===row.asset)?.name||'保留画面';canvas.append(part);}
 const ghost=document.createElement('div');ghost.id='editDropGhost';ghost.className='picture-drop-ghost';ghost.style.top=(trackTop(plan?.clips.find(c=>c.id===clipId)?trackOf(plan.clips.find(c=>c.id===clipId)):drag?.track||mediaDrag?.track||selectedTrack)+6)+'px';ghost.style.left=at/duration*100+'%';ghost.style.width=Math.max(2,length/duration*canvas.clientWidth)+'px';canvas.append(ghost);
 const line=document.createElement('div');line.id='editDropLine';line.className='picture-drop-line';line.style.top=(trackTop(drag?.track||mediaDrag?.track||selectedTrack)-24)+'px';line.style.left=at/duration*100+'%';canvas.append(line);
 const label=document.createElement('div');label.id='editDropLabel';label.className='picture-drop-label';label.style.top=(trackTop(drag?.track||mediaDrag?.track||selectedTrack)-24)+'px';label.textContent=ui.fmt(at)+' · '+(error?'无法放置 · ':'')+(error||note);canvas.append(label);
 const view=$('#editScroll'),x=at/duration*canvas.clientWidth;label.style.left=Math.max(view.scrollLeft+5,Math.min(x+8,view.scrollLeft+view.clientWidth-Math.min(300,view.clientWidth-10)))+'px';label.style.maxWidth=Math.max(120,view.clientWidth-16)+'px';
 $('#editScroll').classList.add('picture-drop-active');$('#editScroll').classList.toggle('picture-drop-invalid',!!error);
 dragStatus.textContent=error||ui.fmt(at)+' · '+note+'；音乐与字幕时间保持不变';
}
function assetClip(a,id,track=selectedTrack){return {id,asset:a.id,start:0,in:0,duration:a.kind==='image'?5:Math.max(1/comp().fps,Math.floor(a.duration*comp().fps)/comp().fps),fit:'contain',x:0,y:0,...(comp().tracks?{track}:{})};}
function assetPlan(a,id,splitId,at,mode,track=selectedTrack){const base=structuredClone(comp());if(!base.assets.some(x=>x.id===a.id))base.assets.push(structuredClone(a));return pictureEdits.insert(base,assetClip(a,id,track),at,{ripple:mode==='insert',splitId});}
function applyPlan(plan,id,label){
 const before=comp(),previous=selected,previousTrack=selectedTrack;state().doc.composition=plan;selected=id;const target=plan.clips.find(c=>c.id===id);if(target)selectedTrack=trackOf(target);
 try{pictureEdits.checked(plan);commit(label);}catch(e){state().doc.composition=before;selected=previous;selectedTrack=previousTrack;render();throw e;}
}
async function useFullVideo(a){const id=projectId;await ui.promptForm('使用整段外部剪辑','<p>使用「'+esc(a.name)+'」，从 0 秒替换当前所有画面轨，按 16:9 画布完整显示。混音、双语字幕、样式、音频偏移和字幕微调保持原位。</p><p>原素材与旧导出保留；当前页面可撤销。画面时长改为 '+ui.fmt(a.duration)+'，请检查音乐与字幕是否适合这个剪辑版。若视频已烧录字幕，请在导出中关闭重复烧录。</p>',async()=>{if(id!==projectId)throw Error('工程已切换，请重新选择');ui.stop();const fps=comp()?.fps||25,clipId=newClipId(),duration=Math.max(1/fps,Math.floor(a.duration*fps)/fps),plan={version:1,fps,width:1920,height:1080,duration,allowGaps:false,assets:[structuredClone(a)],clips:[{id:clipId,asset:a.id,start:0,in:0,duration,fit:'contain',x:0,y:0}]};applyPlan(plan,clipId,'使用整段外部剪辑');ui.notify('document');loaded='';sync(true);window.CWVideoView?.focus('picture');ui.message('整段画面已替换，混音与字幕保留；可撤销，请保存并检查对齐');});}
async function insertAtHead(a){const id=projectId,at=ui.get().position;await ensureEdit();if(id!==projectId||!comp())return;pause();const clipId=newClipId(),plan=assetPlan(a,clipId,newClipId(),Math.min(comp().duration,at),'insert');applyPlan(plan,clipId,'插入播放头画面');window.CWVideoView?.focus('picture');ui.message('画面已插入播放头，后续画面顺延；音乐与字幕保持原位');}
$('#editMedia').addEventListener('dragstart',e=>{
 const el=e.target.closest('[data-media-drag]'),a=el&&library.find(a=>a.id===el.dataset.mediaDrag);
 if(!a||!active()||drag||effectDrag){e.preventDefault();if(a)ui.message('请先启用多素材剪辑，并回到剪辑时间轴');return;}
 pause();mediaDrag={project:projectId,asset:a,id:newClipId(),splitId:newClipId(),mode:dragMode(),plan:null};
 e.dataTransfer.effectAllowed='copy';e.dataTransfer.setData(mediaMime,JSON.stringify({project:projectId,asset:a.id}));e.dataTransfer.setData('text/plain',a.name);
 el.classList.add('media-dragging');window.CWVideoView?.focus('picture');
});
function mediaDragValid(e){return mediaDrag&&mediaDrag.project===projectId&&active()&&[...e.dataTransfer.types].includes(mediaMime);}
function updateMediaDrop(event){
 const d=mediaDrag;if(!d||!comp())return;const track=trackAt(event.clientY),at=snappedTime(pointerTime(event.clientX),event,null,0,track),clip=assetClip(d.asset,d.id,track);d.track=track;
 d.at=at;d.plan=null;try{d.plan=assetPlan(d.asset,d.id,d.splitId,at,d.mode,track);paintDrop(d.plan,d.id,at,clip.duration,d.mode==='insert'?'插入素材，后续画面顺延':'放入空白区间');}
 catch(error){paintDrop(null,d.id,at,clip.duration,'',error.message);}
}
$('#editCanvas').addEventListener('dragover',e=>{if(!mediaDragValid(e)||!e.target.closest('.picture-lane,.picture-ruler,#editDropGhost,#editDropLine,#editDropLabel'))return;e.preventDefault();e.dataTransfer.dropEffect='copy';updateMediaDrop(e);autoScroll(e,updateMediaDrop);});
$('#editScroll').addEventListener('dragleave',e=>{if(!$('#editScroll').contains(e.relatedTarget)){stopScroll();clearDrop();if(mediaDrag)mediaDrag.plan=null;}});
$('#editCanvas').addEventListener('drop',ui.safe(async e=>{
 if(!mediaDragValid(e))return;e.preventDefault();stopScroll();let payload;try{payload=JSON.parse(e.dataTransfer.getData(mediaMime));}catch{cancelMediaDrag();return;}
 const d=mediaDrag;if(payload.project!==d.project||payload.asset!==d.asset.id){cancelMediaDrag();return;}
 if(!e.target.closest('.picture-lane,.picture-ruler,#editDropGhost,#editDropLine,#editDropLabel')){cancelMediaDrag();return;}
 updateMediaDrop(e);const plan=d.plan;cancelMediaDrag();if(!plan)return;applyPlan(plan,d.id,d.mode==='insert'?'拖入画面并插入':'拖入空白画面');ui.message('画面已放置，音乐和字幕保持原位');
}));
function cancelMediaDrag(){stopScroll();mediaDrag=null;clearDrop();$$('.media-dragging').forEach(el=>el.classList.remove('media-dragging'));}
document.addEventListener('dragend',cancelMediaDrag);
$('#editCanvas').addEventListener('pointerdown',e=>{
 if(e.button!==0||!active()||mediaDrag||e.target.closest('[data-transition],[data-end-fade],.picture-track-head'))return;
 const el=e.target.closest('[data-picture]');pause();if(!el){seek(pointerTime(e.clientX));return;}
 selected=el.dataset.picture;const c=selectedClip();selectedTrack=trackOf(c);drag={id:c.id,project:projectId,base:structuredClone(comp()),before:structuredClone(c),edge:e.target.dataset.edge||'move',mode:dragMode(),x:e.clientX,y:e.clientY,scroll:$('#editScroll').scrollLeft,width:$('#editCanvas').clientWidth,target:el,pointer:e.pointerId,moved:false,plan:null};
 el.setPointerCapture(e.pointerId);$$('[data-picture].selected').forEach(row=>row.classList.remove('selected'));el.classList.add('selected');$('#editTargetTrack').value=selectedTrack;inspector();e.preventDefault();
});
function updateClipDrop(e){
 const d=drag;if(!d||d.project!==projectId)return;if(!d.moved&&Math.hypot(e.clientX-d.x,e.clientY-d.y)<3)return;d.moved=true;
 const old=d.before,base=d.base,delta=(e.clientX-d.x+$('#editScroll').scrollLeft-d.scroll)/d.width*base.duration,edge=d.edge;
 const target=edge==='move'?trackAt(e.clientY):trackOf(old);let at=snappedTime(edge==='right'?old.start+old.duration+delta:old.start+delta,e,d.id,edge==='move'?old.duration:0,target);d.track=target;
 d.plan=null;
 try{
  if(edge==='move'&&d.mode==='insert'&&target===trackOf(old)){
   at=pictureEdits.slot(base,pointerTime(e.clientX),d.id,target);const plan=pictureEdits.reorder(base,d.id,at),row=plan.clips.find(c=>c.id===d.id);d.plan=plan;paintDrop(plan,d.id,row.start,row.duration,'插入排序，仅接拢和顺延画面');return;
  }
  const plan=structuredClone(base),c=plan.clips.find(c=>c.id===d.id);
  if(edge==='move'){c.start=Math.max(0,at);if(comp().tracks)c.track=target;if(target!==trackOf(old))delete c.transition;}
  if(edge==='left'){at=Math.max(0,at);const change=at-old.start;c.start=at;c.in=assetFor(c).kind==='image'?0:old.in+change;c.duration=old.duration-change;}
  if(edge==='right')c.duration=Math.max(1/base.fps,at-old.start);
  pictureEdits.checked(plan);d.plan=plan;paintDrop(plan,d.id,c.start,c.duration,edge==='move'?'自由移动，原位置留空':'修剪当前片段');
 }catch(error){paintDrop(null,d.id,Math.max(0,at),old.duration,'',error.message);}
}
$('#editCanvas').addEventListener('pointermove',e=>{if(!drag)return;updateClipDrop(e);autoScroll(e,updateClipDrop);});
function finishDrag(cancel=false){
 if(!drag)return;stopScroll();const d=drag;drag=null;clearDrop();if(d.target.hasPointerCapture(d.pointer))d.target.releasePointerCapture(d.pointer);
 if(!cancel&&!d.moved&&d.project===projectId){for(const id of ['editSplit','editDuplicate','editDelete','editRipple','editEarlier','editLater'])$('#'+id).disabled=!selectedClip();renderTransitions();return;}
 if(cancel||!d.moved||!d.plan||d.project!==projectId){render();return;}
 if(JSON.stringify(d.plan)===JSON.stringify(comp())){render();return;}
 try{applyPlan(d.plan,d.id,d.edge==='move'&&d.mode==='insert'?'拖动片段插入排序':'拖动或修剪画面');}catch(e){ui.message(e.message);}
}
$('#editCanvas').addEventListener('pointerup',()=>finishDrag());$('#editCanvas').addEventListener('pointercancel',()=>finishDrag(true));$('#editCanvas').addEventListener('lostpointercapture',()=>finishDrag(true));
$('#editCanvas').addEventListener('dblclick',e=>{const el=e.target.closest('[data-picture]');if(el){selected=el.dataset.picture;inspector();$('#editInspector').scrollIntoView({block:'nearest'});}});
function cancelPictureGestures(){finishDrag(true);cancelMediaDrag();}
window.addEventListener('keydown',e=>{if(e.key==='Escape'&&(drag||mediaDrag)){e.preventDefault();e.stopImmediatePropagation();cancelPictureGestures();}},true);
window.addEventListener('blur',cancelPictureGestures);
window.addEventListener('cw-video-history-before',cancelPictureGestures);
window.addEventListener('cw-video-change',e=>{if(['visibility','save','document'].includes(e.detail.type))cancelPictureGestures();});

$('#editNew').onclick=ui.safe(()=>ui.promptForm('新建画面剪辑工程','<label>工程名 · 支持中文、日语和空格<input id="editNewName" value="My Cover Edit" maxlength="255"></label><p class="hint">媒体库、画面、混音和双语字幕分轨保存。原工程保持原样。</p>',async()=>{if(state().dirty)await ui.save();const p=await ui.api('/api/video-create/new',{name:$('#editNewName').value,mode:'edit'});await ui.open(p.id);}));
$('#editCopy').onclick=ui.safe(()=>ui.promptForm('保留原工程，创建剪辑副本','<label>副本名 · 支持中文、日语和空格<input id="editCopyName" value="'+esc((state().doc?.name||'Video').slice(0,55)+' Edit')+'" maxlength="255"></label><p class="hint">复制磁盘上已保存的字幕、样式与对齐参数。当前未保存编辑需先保存；此操作本身不会写入原工程。</p>',async()=>{if(state().dirty)throw Error('请先保存当前编辑，再创建副本');const p=await ui.api('/api/video-edit-copy/'+state().doc.id,{revision:state().doc.revision,name:$('#editCopyName').value});await ui.open(p.id);}));
async function opened(){cancelPictureGestures();const s=state(),id=s.doc?.id;if(!id)return;const initialized=projectId===id;if(!initialized){pause();projectId=id;position=0;selected=null;selectedTrack='V1';loaded='';library=[];lastImported=[];renderLibrary();}const token=++request;render();const rows=await ui.api('/api/video-library/'+id);if(token!==request||projectId!==id)return;library=rows;renderLibrary();if(comp()){if(!initialized)load(s.doc);else sync(true);}}
window.addEventListener('cw-video-change',e=>{const type=e.detail.type;if(type==='open')opened().catch(e=>ui.message(e.message));else if(type==='history'||type==='save'){loaded='';render();if(active())sync(true);}else if(type==='edit'&&!drag&&!effectDrag)render();if(state().exact){transitionCanvas.hidden=true;for(const m of transitionMedia.values())if(m.node.tagName==='VIDEO')m.node.pause();image.hidden=true;ui.player.hidden=false;}});
window.addEventListener('cw-workbench-exit',()=>{cancelPictureGestures();closed=true;pause();});new ResizeObserver(()=>{if(comp()&&!drag&&!effectDrag&&!mediaDrag)render();}).observe($('#editScroll'));
ui.cover.addEventListener('loadedmetadata',()=>{if(active())render();});
window.CWVideoEdit={isPlaying:()=>playing,active,clock,pause,seek,sync,load,toggle,importPath};ui.ready.then(()=>{if(!projectId&&state().doc)opened().catch(e=>ui.message(e.message));});
})();
