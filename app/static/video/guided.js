/* Guided readiness checks, a video-time caption strip, and local font specimens. */
(() => {
'use strict';
const ui=window.CWVideoStudio;if(!ui)return;
const timing=window.CWCaptionTiming;
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let checks=null,active=null,request=0,debounce=null,closed=false,zoom=1,zoomMode='auto',drag=null,animation=null,expanded=true,hovered=null,activeLane='original',editing=null,manualUntil=0;
const guide=$('#videoGuide'),host=$('#subtitleTimeline');
const num=v=>Number.isFinite(Number(v))?Number(v):0;
function panel(name,target){$(`[data-panel="${name}"]`)?.click();const el=target?$(target):$('#'+name);el?.scrollIntoView({block:'nearest',behavior:'smooth'});if(el?.matches('input'))el.focus();}
function button(action,label,disabled=false){return `<button type="button" class="quiet" data-guide-action="${action}" ${disabled?'disabled':''}>${label}</button>`;}
function guideView(){
 const {doc,dirty}=ui.get();if(!doc||!checks)return;
 if(!active)active=checks.steps.find(s=>!s.done)?.id||'export';
 const step=checks.steps.find(s=>s.id===active)||checks.steps[0];
 const labels={audio:'跟随混音时间',video:'固定视频时间',unknown:'尚未确认'};
 let actions='';
 if(step.id==='mv')actions=button('download','粘贴链接下载 MV')+button('video','选择本地视频');
 if(step.id==='mix')actions=button('audio','选择最终混音');
 if(step.id==='align')actions=button('analyze','测量偏移与响度')+button('alignment','已试听三段，确认对齐')+button('aligned-audio',checks.audioAligned?'取消音轨已对齐标记':'此音轨已经对齐视频，锁定偏移为 0');
 if(step.id==='captions'){
  actions=button('captions','导入双语字幕')+button('table','定位字幕表')+button('single-language',doc.workflow?.singleLanguage?'恢复双语要求':'本曲只用单语字幕');
  if(doc.cues.length&&checks.blockers.length)actions+=button('video-clock','确认现有字幕已是视频时间，不再加偏移');
  if(checks.blockers.some(x=>x.includes('可能重复')))actions+=button('clear-shift','清零字幕额外微调')+button('ack-shift','此微调确实是额外移动');
 }
 if(step.id==='preview')actions=button('layout','调整样式与字体')+button('preview','生成准确区间预览')+button('preview-reviewed','已播放本版预览并检查',!checks.previewReady);
 if(step.id==='export')actions=button('output','查看导出规格')+button('export','合成完整新版本');
 let timing=`字幕时间基准：${labels[checks.captionClock]||labels.unknown}`;
 if(checks.captionClock==='audio')timing+=` · 已计入音频偏移 ${checks.appliedAudioOffset>=0?'+':''}${checks.appliedAudioOffset.toFixed(3)} 秒，勿再填入字幕微调`;
 if(checks.pendingDelta)timing+=` · 保存后只补 ${checks.pendingDelta>0?'+':''}${checks.pendingDelta.toFixed(3)} 秒差值`;
 guide.innerHTML=`<div class="guide-heading"><div><span class="eyebrow">ONE SONG, SIX STEPS</span><h2>跟着做，少漏一步。</h2></div><div><span>${checks.completed} / 6 已就绪${dirty?' · 含未保存修改':''}</span><button type="button" class="quiet" id="guideToggle">${expanded?'收起步骤说明':'展开步骤说明'}</button></div></div><nav class="guide-steps" aria-label="制作步骤">${checks.steps.map((s,i)=>`<button type="button" data-step="${s.id}" class="${s.done?'done ':''}${active===s.id?'current':''}" aria-current="${active===s.id?'step':'false'}"><b>${s.done?'✓':String(i+1).padStart(2,'0')}</b><span>${s.title}<small>${s.done?'已就绪':s.missing.length+' 项待处理'}</small></span></button>`).join('')}</nav><div class="guide-detail" ${expanded?'':'hidden'}><div><strong>${step.title}</strong><p>${esc(step.detail)}</p>${step.missing.length?'<ul>'+step.missing.map(m=>`<li>${esc(m)}</li>`).join(''):'<p class="guide-ok">本步已就绪；实际翻译、听感与画面仍由你确认。</p>'}</div><div class="guide-actions">${actions}<button type="button" id="guideNext">下一步 →</button></div></div><div class="timing-ledger ${checks.blockers.length?'needs-review':''}" role="status">${esc(timing)}<span>字幕表与下方时间轴始终显示视频时间。</span></div>`;
 $('#guideToggle').onclick=()=>{expanded=!expanded;guideView();};
 $$('[data-step]').forEach(b=>b.onclick=()=>{active=b.dataset.step;expanded=true;guideView();});
 $('#guideNext').onclick=()=>{const i=checks.steps.findIndex(s=>s.id===active);active=checks.steps[Math.min(i+1,5)].id;guideView();};
 $$('[data-guide-action]').forEach(b=>b.onclick=ui.safe(async()=>{
  const action=b.dataset.guideAction;
  if(action==='video'||action==='audio'){panel('sources','#'+action);return;}
  if(action==='download'){panel('sources');$('#sources details').open=true;$('#url').focus();return;}
  if(['analyze','captions','preview','export'].includes(action)){$('#'+action).click();return;}
  if(action==='layout'){panel('layout');return;}
  if(action==='output'){panel('output');return;}
  if(action==='table'){$('#cueList').scrollIntoView({behavior:'smooth',block:'center'});return;}
  if(action==='clear-shift'){$('#subtitleShift').value=0;$('#subtitleShift').dispatchEvent(new Event('input'));await ui.save();return;}
  await ui.review(action==='preview-reviewed'?'preview':action);await refreshChecks();
 }));
}
async function refreshChecks(){
 const state=ui.get();if(!state.doc||closed||!state.visible)return;const token=++request,id=state.doc.id;
 try{const result=await ui.api('/api/video-check/'+encodeURIComponent(id),state.doc);if(token!==request||ui.get().doc?.id!==id)return;checks=result;guideView();}
 catch(e){if(token===request)guide.innerHTML=`<p class="error">引导检查未完成：${esc(e.message)}</p>`;}
}
function scheduleChecks(){clearTimeout(debounce);debounce=setTimeout(refreshChecks,350);}

host.innerHTML=`<div class="subtitle-strip-head"><strong>字幕时间轴 <span>原文 / 译文</span></strong><div><button class="quiet" data-history="undo" disabled>↶ 撤销</button><button class="quiet" data-history="redo" disabled>↷ 重做</button><button class="quiet" id="captionPrev" aria-label="上一句字幕">←</button><button class="quiet" id="captionNext" aria-label="下一句字幕">→</button><button class="quiet" id="captionFollow">定位播放头</button></div></div><div class="caption-zoom-bar"><span>字幕缩放</span><button class="quiet" id="captionZoomOut" aria-label="缩小字幕时间轴">− 缩小</button><input id="captionZoomSlider" type="range" min="0" max="6" step="0.125" aria-label="字幕缩放滑块"><button id="captionZoomIn" aria-label="放大字幕时间轴">放大 ＋</button><select id="captionZoom" aria-label="字幕时间轴缩放"><option value="auto">校对视图 · 约 20 秒</option><option value="1">全曲</option><option value="2">2×</option><option value="4">4×</option><option value="8">8×</option><option value="16">16×</option><option value="32">32×</option><option value="64">64×</option><option value="custom" disabled>自定义缩放</option></select></div><div class="caption-edit-options"><label class="check"><input type="checkbox" id="captionAutoFollow" checked>跟随播放</label><label class="check"><input type="checkbox" id="captionSnap" checked>边缘吸附</label><label class="check" title="关闭时只调整拖动的语言行；开启时双语同步调整"><input type="checkbox" id="captionLink">双语联动</label><span id="captionSnapStatus">Alt 临时关闭吸附 · 双击字幕改文字</span></div><input type="range" id="captionOverview" aria-label="全曲字幕播放位置" min="0" max="1" step="0.01" value="0"><div id="captionScroll" class="caption-scroll"><div id="captionCanvas" class="caption-canvas"></div></div><div class="caption-window-bar"><button class="quiet" id="captionPagePrev" aria-label="浏览前一屏字幕">◀ 前一屏</button><span id="captionWindow" aria-live="off"></span><button class="quiet" id="captionPageNext" aria-label="浏览后一屏字幕">后一屏 ▶</button></div><div class="caption-readout" id="captionReadout"></div><p class="hint">点「放大」或拖动缩放滑块展开字幕；Ctrl + 滚轮围绕鼠标位置缩放。横向滚动或用「前一屏 / 后一屏」浏览。点击字幕选句，拖动字幕或两侧边缘调整时间；Ctrl + Z 撤销，Ctrl + Y 重做。</p>`;
const viewport=$('#captionScroll'),canvas=$('#captionCanvas');
function duration(){const s=ui.get();const recorded=s.jobs.map(j=>j.result?.sourceVideo?.duration).find(Number.isFinite);return Math.max(1,s.duration||recorded||0,...(s.doc?.cues||[]).map(r=>num(timing.bounds(r).end)+num(s.doc.subtitleShift)),num($('#out').value));}
function geometry(){const total=duration();if(zoomMode==='auto')zoom=Math.max(1,Math.min(64,total/20));return {duration:total,width:Math.max(1,viewport.clientWidth)*zoom};}
function location(clientX){const g=drag?.geometry||geometry();return Math.max(0,Math.min(g.duration,(clientX-viewport.getBoundingClientRect().left+viewport.scrollLeft)/g.width*g.duration));}
function position(el,start,end,g){el.style.left=(start/g.duration*100)+'%';el.style.width=Math.max(.1,(end-start)/g.duration*100)+'%';}
function renderTimeline(){
 const s=ui.get();if(!s.doc||drag||closed)return;const g=geometry(),shift=num(s.doc.subtitleShift);canvas.style.width=g.width+'px';
 syncZoomControls();
 const tick=[.5,1,2,5,10,15,30,60,120,300,600].find(t=>t/g.duration*g.width>=65)||600;
 let ruler='';for(let t=0;t<=g.duration;t+=tick)ruler+=`<span style="left:${t/g.duration*100}%">${ui.fmt(t).slice(0,tick<1?-2:-4)}</span>`;
 const lanes=['original','translation'].map((key,i)=>`<div class="caption-lane lane-${key}" aria-label="${i?'译文':'原文'}字幕轨">${s.doc.cues.filter(r=>r[key]&&Number.isFinite(timing.get(r,key).start)&&timing.get(r,key).end>timing.get(r,key).start).map(r=>{
  const range=timing.get(r,key),start=range.start+shift,end=range.end+shift;return `<div role="button" tabindex="0" data-caption="${esc(r.id)}" data-language="${key}" class="caption-block ${r.id===s.selected?'selected':''}" style="left:${start/g.duration*100}%;width:${Math.max(.1,(end-start)/g.duration*100)}%" title="${esc(r.id+' · '+ui.fmt(start)+' — '+ui.fmt(end)+'\n'+r.original+'\n'+r.translation)}" aria-label="${esc(r.id+' '+r[key])}"><span class="caption-edge left" data-edge="start" role="slider" tabindex="0" aria-label="${esc(r.id)} 调整开始时间" aria-valuemin="0" aria-valuemax="${g.duration}" aria-valuenow="${start}"></span><span class="caption-words">${esc(r[key])}</span><button type="button" class="caption-edit" aria-label="编辑 ${esc(r.id)} ${key==='original'?'原文':'译文'}" title="编辑文字" data-edit="${key}">✎</button><span class="caption-edge right" data-edge="end" role="slider" tabindex="0" aria-label="${esc(r.id)} 调整结束时间" aria-valuemin="0" aria-valuemax="${g.duration}" aria-valuenow="${end}"></span></div>`;}).join('')}</div>`).join('');
 canvas.innerHTML=`<div class="caption-ruler" id="captionRuler">${ruler}</div><div class="caption-loop" id="captionLoop"><span data-loop="in" title="拖动循环入点 I">I</span><span data-loop="out" title="拖动循环出点 O">O</span></div>${lanes}<div id="captionPlayhead" class="caption-playhead"></div><div id="captionSnapGuide" class="caption-snap-guide" hidden></div>`;
 $('#captionRuler').onpointerdown=e=>ui.seek(location(e.clientX));
 $$('[data-caption]').forEach(el=>{
  el.onpointerdown=e=>{if(e.button!==0||e.target.closest('[data-edit]'))return;e.preventDefault();closeEditor(false);const row=s.doc.cues.find(r=>r.id===el.dataset.caption);activeLane=el.dataset.language;ui.history.begin('调整'+(activeLane==='original'?'原文':'译文')+'时间');drag={kind:'caption',geometry:g,id:row.id,lane:activeLane,linked:$('#captionLink').checked,edge:e.target.dataset.edge,base:{start:row.start,end:row.end},ranges:Object.fromEntries(timing.languages.map(k=>[k,{...timing.get(row,k)}])),at:location(e.clientX),x:e.clientX,moved:false};el.setPointerCapture(e.pointerId);};
  el.onpointerenter=()=>{hovered=el.dataset.caption;activeLane=el.dataset.language;tickPosition();};el.onpointerleave=()=>{if(!drag){hovered=null;tickPosition();}};el.onpointermove=move;el.onpointerup=finish;el.onpointercancel=finish;
  el.ondblclick=e=>{e.preventDefault();openEditor(el.dataset.caption,el.dataset.language,el.getBoundingClientRect());};
  el.querySelector('[data-edit]').onclick=e=>{e.stopPropagation();openEditor(el.dataset.caption,el.dataset.language,el.getBoundingClientRect());};
  el.onkeydown=e=>{if(e.target.closest('[data-edit]'))return;const row=s.doc.cues.find(r=>r.id===el.dataset.caption);if(['Enter','F2'].includes(e.key)){e.preventDefault();openEditor(row.id,el.dataset.language,el.getBoundingClientRect());return;}if(!['ArrowLeft','ArrowRight'].includes(e.key))return;e.preventDefault();const step=(e.shiftKey?.5:.05)*(e.key==='ArrowLeft'?-1:1),edge=e.target.dataset.edge;const state={base:{start:row.start,end:row.end},ranges:Object.fromEntries(timing.languages.map(k=>[k,{...timing.get(row,k)}])),lane:el.dataset.language,linked:$('#captionLink').checked};applyDelta(row,state,step,edge);ui.renderRows();ui.mark({label:'微调字幕时间'});renderTimeline();const replacement=$$('[data-caption]').find(node=>node.dataset.caption===row.id&&node.dataset.language===state.lane);(edge?replacement?.querySelector('[data-edge="'+edge+'"]'):replacement)?.focus({preventScroll:true});};
 });
 $$('[data-loop]').forEach(el=>{el.onpointerdown=e=>{e.preventDefault();drag={kind:'loop',geometry:g,edge:el.dataset.loop};el.setPointerCapture(e.pointerId);};el.onpointermove=move;el.onpointerup=finish;el.onpointercancel=finish;});
 tickPosition();
}
function applyDelta(row,state,delta,edge){
 const ranges=state.linked?[state.base,...Object.values(state.ranges)]:[state.ranges[state.lane]];
 const minimum=Math.min(...ranges.map(r=>r.start)),maximum=Math.max(...ranges.map(r=>r.end));
 let ds=0,de=0;
 if(edge==='start')ds=Math.max(-minimum,Math.min(delta,...ranges.map(r=>r.end-r.start-.02)));
 else if(edge==='end')de=Math.max(delta,...ranges.map(r=>r.start+.02-r.end)),de=Math.min(de,86400-maximum);
 else ds=de=Math.max(-minimum,Math.min(delta,86400-maximum));
 if(state.linked){row.start=Math.round((state.base.start+ds)*1000)/1000;row.end=Math.round((state.base.end+de)*1000)/1000;for(const k of timing.languages)timing.set(row,k,{start:state.ranges[k].start+ds,end:state.ranges[k].end+de});}
 else timing.set(row,state.lane,{start:state.ranges[state.lane].start+ds,end:state.ranges[state.lane].end+de});
}
function snapDelta(delta,e){
 const indicator=$('#captionSnapGuide');indicator.hidden=true;$('#captionSnapStatus').textContent='Alt 临时关闭吸附 · 双击字幕改文字';
 if(!$('#captionSnap').checked||e.altKey)return delta;
 const s=ui.get(),shift=num(s.doc.subtitleShift),range=drag.ranges[drag.lane],threshold=Math.min(.12,8/drag.geometry.width*drag.geometry.duration);
 const targets=s.doc.cues.filter(r=>r.id!==drag.id&&r[drag.lane]).flatMap(r=>['start','end'].map(edge=>({time:timing.get(r,drag.lane)[edge]+shift,label:r.id+(edge==='start'?' 开始':' 结束')})));
 targets.push({time:s.position,label:'播放头'});
 let best=null;
 for(const edge of drag.edge?[drag.edge]:['start','end'])for(const target of targets){const adjustment=target.time-(range[edge]+shift+delta);if(Math.abs(adjustment)>threshold||best&&Math.abs(adjustment)>=Math.abs(best.adjustment))continue;const candidate={...s.doc.cues.find(r=>r.id===drag.id)};applyDelta(candidate,drag,delta+adjustment,drag.edge);if(Math.abs(timing.get(candidate,drag.lane)[edge]+shift-target.time)>.001)continue;best={...target,adjustment};}
 if(best){indicator.hidden=false;indicator.style.left=best.time/drag.geometry.duration*100+'%';$('#captionSnapStatus').textContent='吸附到 '+best.label+' · '+ui.fmt(best.time);return delta+best.adjustment;}
 return delta;
}
function move(e){
 if(!drag)return;const s=ui.get(),g=drag.geometry,at=location(e.clientX);
 if(drag.kind==='loop'){
  const a=num($('#in').value),b=num($('#out').value);
  $('#'+drag.edge).value=(drag.edge==='in'?Math.min(b-.05,at):Math.max(a+.05,at)).toFixed(3);tickPosition();return;
 }
 if(Math.abs(e.clientX-drag.x)<3&&!drag.moved)return;drag.moved=true;
 const row=s.doc.cues.find(r=>r.id===drag.id),delta=snapDelta((at-drag.at),e);applyDelta(row,drag,delta,drag.edge);
 $$('[data-caption]').filter(el=>el.dataset.caption===row.id).forEach(el=>{const range=timing.get(row,el.dataset.language);position(el,range.start+num(s.doc.subtitleShift),range.end+num(s.doc.subtitleShift),g);el.querySelector('[data-edge="start"]').setAttribute('aria-valuenow',range.start+num(s.doc.subtitleShift));el.querySelector('[data-edge="end"]').setAttribute('aria-valuenow',range.end+num(s.doc.subtitleShift));});
 ui.mark();tickPosition();
}
function finish(){if(!drag)return;const previous=drag;if(previous.kind==='caption'){if(previous.moved)ui.renderRows();ui.select(previous.id,!previous.moved,previous.lane);}drag=null;if(previous.kind==='caption')ui.history.end();if(previous.moved||previous.kind==='loop')renderTimeline();else tickPosition();$('#captionSnapGuide').hidden=true;$('#captionSnapStatus').textContent='Alt 临时关闭吸附 · 双击字幕改文字';}
function tickPosition(){
 const s=ui.get();if(!s.doc||closed)return;const g=geometry(),t=s.position,head=$('#captionPlayhead');if(head)head.style.left=(t/g.duration*100)+'%';
 const overview=$('#captionOverview');overview.max=g.duration;overview.value=t;
 const a=num($('#in').value),b=num($('#out').value),loop=$('#captionLoop');if(loop){position(loop,a,b,g);loop.classList.toggle('enabled',$('#loop').checked);}
 const cueMap=new Map(s.doc.cues.map(r=>[r.id,r]));$$('[data-caption]').forEach(el=>{const r=cueMap.get(el.dataset.caption);const range=r?timing.get(r,el.dataset.language):null;el.classList.toggle('playing',!!range&&t>=range.start+num(s.doc.subtitleShift)&&t<range.end+num(s.doc.subtitleShift));el.classList.toggle('selected',r?.id===s.selected);});
 const playing=s.doc.cues.find(r=>r[activeLane]&&t>=timing.get(r,activeLane).start+num(s.doc.subtitleShift)&&t<timing.get(r,activeLane).end+num(s.doc.subtitleShift));
 const row=s.doc.cues.find(r=>r.id===(editing?.id||hovered))||(!ui.player.paused?playing:null)||s.doc.cues.find(r=>r.id===s.selected)||playing;
 $('#captionReadout').innerHTML=row?`<b>${esc(row.id)} · ${ui.fmt(timing.get(row,activeLane).start+num(s.doc.subtitleShift))} — ${ui.fmt(timing.get(row,activeLane).end+num(s.doc.subtitleShift))}</b><span>${esc(row.original)}</span><span>${esc(row.translation)}</span>`:'<span>点击字幕块查看完整原文和译文。</span>';
 maybeFollow();windowRange();
}
function windowRange(){const g=geometry(),start=viewport.scrollLeft/g.width*g.duration,end=Math.min(g.duration,(viewport.scrollLeft+viewport.clientWidth)/g.width*g.duration);$('#captionWindow').textContent=`${ui.fmt(start).slice(0,-2)} — ${ui.fmt(end).slice(0,-2)} · ${(end-start).toFixed(1)} 秒 / 屏`;$('#captionPagePrev').disabled=viewport.scrollLeft<1;$('#captionPageNext').disabled=viewport.scrollLeft+viewport.clientWidth>=viewport.scrollWidth-1;}
function syncZoomControls(){const preset=[1,2,4,8,16,32,64].find(n=>Math.abs(n-zoom)<.0001);$('#captionZoom').value=zoomMode==='auto'?'auto':preset?String(preset):'custom';$('#captionZoomSlider').value=Math.log2(zoom);$('#captionZoomIn').disabled=zoom>=64;$('#captionZoomOut').disabled=zoom<=1;$('#captionZoomSlider').setAttribute('aria-valuetext',zoom.toFixed(1)+' 倍');}
function saveZoom(){try{localStorage.setItem('cw-caption-zoom:'+ui.get().doc.id,JSON.stringify({mode:zoomMode,zoom,follow:$('#captionAutoFollow').checked,snap:$('#captionSnap').checked,linked:$('#captionLink').checked}));}catch{}}
function setZoom(value,mode='manual',at=ui.get().position,pixel=viewport.clientWidth*.4){zoomMode=mode;zoom=Math.max(1,Math.min(64,value));renderTimeline();const g=geometry();viewport.scrollLeft=Math.max(0,at/g.duration*g.width-pixel);windowRange();saveZoom();}
function follow(){const g=geometry(),x=ui.get().position/g.duration*g.width;viewport.scrollLeft=Math.max(0,x-viewport.clientWidth*.4);windowRange();}
function maybeFollow(){if(!$('#captionAutoFollow').checked||ui.player.paused||drag||editing||zoom<=1||Date.now()<manualUntil)return;const g=geometry(),x=ui.get().position/g.duration*g.width;if(x<viewport.scrollLeft+8||x>viewport.scrollLeft+viewport.clientWidth*.82)follow();}
for(const id of ['captionAutoFollow','captionSnap','captionLink'])$('#'+id).onchange=()=>{saveZoom();if(id==='captionAutoFollow'&&$('#'+id).checked){manualUntil=0;follow();}};
viewport.addEventListener('pointerdown',()=>{manualUntil=Date.now()+3000;});
$('#captionZoom').onchange=()=>{const value=$('#captionZoom').value;setZoom(value==='auto'?1:Number(value),value==='auto'?'auto':'manual');};$('#captionFollow').onclick=follow;
$('#captionZoomIn').onclick=()=>setZoom(zoom*2);$('#captionZoomOut').onclick=()=>setZoom(zoom/2);
$('#captionZoomSlider').oninput=()=>setZoom(2**Number($('#captionZoomSlider').value));
viewport.addEventListener('wheel',e=>{if(!e.ctrlKey){manualUntil=Date.now()+3000;return;}e.preventDefault();const at=location(e.clientX),pixel=e.clientX-viewport.getBoundingClientRect().left;setZoom(zoom*2**(-Math.max(-400,Math.min(400,e.deltaY))/400),'manual',at,pixel);},{passive:false});
viewport.addEventListener('scroll',windowRange);
for(const [id,direction] of [['captionPagePrev',-1],['captionPageNext',1]])$('#'+id).onclick=()=>{manualUntil=Date.now()+3000;viewport.scrollLeft+=direction*viewport.clientWidth*.85;windowRange();};
$('#captionOverview').oninput=()=>{ui.seek(num($('#captionOverview').value));tickPosition();follow();};
for(const [id,direction] of [['captionPrev',-1],['captionNext',1]])$('#'+id).onclick=()=>{const s=ui.get();if(!s.doc?.cues.length)return;const sorted=[...s.doc.cues].sort((a,b)=>timing.get(a,activeLane).start-timing.get(b,activeLane).start);let i=sorted.findIndex(r=>r.id===s.selected);if(i>=0)i+=direction;else if(direction>0){i=sorted.findIndex(r=>timing.get(r,activeLane).start+num(s.doc.subtitleShift)>s.position+.0001);if(i<0)i=sorted.length-1;}else{i=sorted.findLastIndex(r=>timing.get(r,activeLane).start+num(s.doc.subtitleShift)<s.position-.0001);}i=Math.max(0,Math.min(sorted.length-1,i));ui.select(sorted[i].id,true,activeLane);renderTimeline();follow();};
for(const id of ['in','out','loop'])$('#'+id).addEventListener('input',()=>{renderTimeline();follow();});
function animate(){tickPosition();if(!ui.player.paused&&!closed)animation=requestAnimationFrame(animate);}
ui.player.addEventListener('timeupdate',tickPosition);
ui.player.addEventListener('seeked',()=>{if($('#captionAutoFollow').checked)follow();});
new ResizeObserver(()=>{renderTimeline();follow();}).observe(viewport);

// Edit at the timeline without hunting for the corresponding table row.
const textEditor=document.createElement('dialog');textEditor.id='captionTextEditor';textEditor.className='caption-text-editor';
textEditor.innerHTML='<div class="preview-head"><strong id="captionTextTitle"></strong><button type="button" class="quiet" id="captionTextCancel" aria-label="取消字幕文字编辑">取消</button></div><textarea id="captionTextInput" maxlength="2000" aria-label="时间轴字幕文字"></textarea><p class="hint">文字即时更新预览；Ctrl + Enter 完成，Esc 取消本次修改。Ctrl + Z 撤销并收起编辑。保存工程后保留。</p><button type="button" id="captionTextDone">完成</button>';
document.body.append(textEditor);
function closeEditor(cancel){if(!editing)return;const previous=editing;editing=null;if(cancel&&ui.get().doc?.id===previous.project){const row=ui.get().doc.cues.find(r=>r.id===previous.id);if(row){row[previous.lane]=previous.text;ui.renderRows();ui.mark();}}textEditor.close();ui.history.end();}
function openEditor(id,lane,rect){closeEditor(false);const state=ui.get(),row=state.doc.cues.find(r=>r.id===id);if(!row)return;activeLane=lane;ui.player.pause();ui.select(id,false,lane);ui.history.begin('修改'+(lane==='original'?'原文':'译文')+'文字');editing={id,lane,project:state.doc.id,text:row[lane]};$('#captionTextTitle').textContent=(lane==='original'?'编辑原文':'编辑译文')+' · '+id;$('#captionTextInput').value=row[lane];textEditor.show();textEditor.style.left=Math.max(12,Math.min(rect.left,innerWidth-textEditor.offsetWidth-12))+'px';textEditor.style.top=Math.max(12,Math.min(rect.bottom+8,innerHeight-textEditor.offsetHeight-12))+'px';$('#captionTextInput').focus();$('#captionTextInput').select();}
$('#captionTextInput').oninput=()=>{if(!editing||ui.get().doc?.id!==editing.project)return;const row=ui.get().doc.cues.find(r=>r.id===editing.id);if(!row)return;row[editing.lane]=$('#captionTextInput').value;ui.renderRows();ui.mark();};
$('#captionTextInput').onkeydown=e=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();closeEditor(true);}else if(e.ctrlKey&&e.key==='Enter'){e.preventDefault();closeEditor(false);}};
$('#captionTextDone').onclick=()=>closeEditor(false);$('#captionTextCancel').onclick=()=>closeEditor(true);
window.addEventListener('cw-video-history-before',()=>{finish();closeEditor(false);});
textEditor.addEventListener('cancel',e=>{e.preventDefault();closeEditor(true);});

// The labels are translated; CSS and FFmpeg still receive the actual local family name.
const fontDialog=document.createElement('dialog');fontDialog.id='fontPreviewDialog';fontDialog.innerHTML='<div class="preview-head"><div><span class="eyebrow">SEE THE TYPE</span><h2>先看字形，再选字体。</h2></div><button id="fontClose" type="button" class="quiet">关闭</button></div><label>预览文字<input id="fontSample" value="让每一句，落在对的时间。 Aa 123 · かな"></label><div class="pair"><label>搜索字体<input id="fontSearch" placeholder="微软雅黑 / 黑体 / 宋体"></label><label>示例字号<input id="fontSize" type="range" min="18" max="48" value="28"></label></div><div id="fontSpecimens"></div><p class="hint">仅可选择本机检测到的字体。未安装的字体不会冒充实际字形；预览中的部分外文可能使用系统后备字体。成片效果请以准确渲染预览为准。</p>';document.body.append(fontDialog);
let fontTarget=null;
function specimens(){
 const s=ui.get(),query=$('#fontSearch').value.trim().toLowerCase(),sample=$('#fontSample').value||'让每一句，落在对的时间。';
 const list=s.fontCatalog.filter(f=>(!query?f.common:(f.label+' '+f.family).toLowerCase().includes(query))).slice(0,60);
 $('#fontSpecimens').innerHTML=list.map((f,i)=>`<button type="button" class="font-specimen ${f.available?'':'unavailable'}" data-font-index="${i}" ${f.available?'':'disabled'}><span class="font-name">${esc(f.label)}<small>${f.available?'点击应用':'未安装，无法展示真实字形'}</small></span><span class="font-sample" data-specimen="${i}"></span></button>`).join('');
 list.forEach((f,i)=>{const span=$(`[data-specimen="${i}"]`);if(!f.available){span.textContent='请安装后再预览';return;}span.textContent=sample;span.style.fontFamily=f.family;span.style.fontSize=$('#fontSize').value+'px';});
 $$('[data-font-index]').forEach(b=>b.onclick=()=>{const f=list[Number(b.dataset.fontIndex)];ui.setFont(...fontTarget,f.family);fontDialog.close();ui.message('已应用 '+f.label);});
}
document.addEventListener('click',e=>{const b=e.target.closest('[data-font-browse]');if(!b)return;fontTarget=b.dataset.fontBrowse.split(':');$('#fontSearch').value='';specimens();fontDialog.showModal();});
for(const id of ['fontSearch','fontSample','fontSize'])$('#'+id).oninput=specimens;$('#fontClose').onclick=()=>fontDialog.close();
window.addEventListener('cw-video-change',e=>{
 if(e.detail.type==='open'){closeEditor(false);active=null;hovered=null;zoom=1;zoomMode='auto';manualUntil=0;$('#captionAutoFollow').checked=true;$('#captionSnap').checked=true;$('#captionLink').checked=false;try{const saved=JSON.parse(localStorage.getItem('cw-caption-zoom:'+ui.get().doc.id));if(saved&&['auto','manual'].includes(saved.mode)&&Number.isFinite(saved.zoom)){zoomMode=saved.mode;zoom=Math.max(1,Math.min(64,saved.zoom));$('#captionAutoFollow').checked=saved.follow!==false;$('#captionSnap').checked=saved.snap!==false;$('#captionLink').checked=saved.linked===true;}}catch{}checks=null;expanded=!(ui.get().doc?.video&&ui.get().doc?.audio&&ui.get().doc?.cues.length);}
 if(e.detail.type==='play'){cancelAnimationFrame(animation);animation=requestAnimationFrame(animate);return;}
 if(e.detail.type==='pause'){cancelAnimationFrame(animation);tickPosition();return;}
 renderTimeline();if(e.detail.type==='open')follow();scheduleChecks();
});
window.addEventListener('focus',()=>refreshChecks());
const checkTimer=setInterval(()=>{if(!document.hidden&&ui.get().visible)refreshChecks();},12000);
window.addEventListener('cw-workbench-exit',()=>{closed=true;clearTimeout(debounce);clearInterval(checkTimer);cancelAnimationFrame(animation);closeEditor(false);request++;});
})();
