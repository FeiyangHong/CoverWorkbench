/* Applied sources, original-sound monitoring and optional timeline waveforms. */
(() => {
'use strict';
const ui=window.CWVideoStudio,$=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const sound=document.createElement('audio');sound.id='sourceSound';sound.preload='auto';document.body.append(sound);
let closed=false,project='',prefs={},loadedSound='',loadingSound='',readySound=false,soundToken=0,proxyToken=0,proxyKey='',proxyURL='',scheduled=false;
const audioCache=new Map(),waveCache=new Map(),videoCache=new Map();
const waveQueue=[];let waveRunning=0;
const defaults={picture:true,mix:true,source:false,original:true,translation:true};
const tracks=document.createElement('details');tracks.className='monitor-track-menu';tracks.id='monitorTracks';
tracks.innerHTML='<summary>轨道显示</summary><div><button type="button" class="quiet" id="monitorAll">全部轨道</button><button type="button" class="quiet" id="monitorCaptionsOnly">只看字幕</button>'+Object.entries({picture:'画面概览',mix:'混音波形',source:'原视频波形',original:'原文字幕',translation:'译文字幕'}).map(([key,label])=>`<label><input type="checkbox" data-monitor-track="${key}">${label}</label>`).join('')+'<small>仅改变本机视图，不影响导出。</small></div>';
$('.editor-view-toolbar').append(tracks);
const listening=$('#listen').closest('label');listening.classList.add('monitor-listen');$('.transport').append(listening);listening.title='监听切换不影响导出；成片仍使用选定的翻唱混音';
const soundStatus=document.createElement('small');soundStatus.id='sourceSoundStatus';soundStatus.setAttribute('role','status');$('.preview-monitor').append(soundStatus);
function state(){return ui.get();}
function persist(){try{localStorage.setItem('cw-video-tracks:'+project,JSON.stringify(prefs));}catch{}}
function paintPreferences(){
 for(const key of Object.keys(defaults)){document.body.classList.toggle('hide-monitor-'+key,!prefs[key]);$('[data-monitor-track="'+key+'"]').checked=!!prefs[key];}
 persist();schedule();
}
tracks.querySelectorAll('input').forEach(input=>input.onchange=()=>{prefs[input.dataset.monitorTrack]=input.checked;paintPreferences();});
$('#monitorAll').onclick=()=>{prefs={...defaults,source:true};paintPreferences();};
$('#monitorCaptionsOnly').onclick=()=>{prefs={picture:false,mix:false,source:false,original:true,translation:true};window.CWVideoView?.focus('captions');paintPreferences();};
function descriptor(t=state().position){
 const doc=state().doc;if(!doc)return null;
 if(doc.composition){const c=window.CWPictureEdits.front(doc.composition,t).clip,a=c&&doc.composition.assets.find(a=>a.id===c.asset);return a?.kind==='video'?{path:a.path,asset:a.id,time:c.in+t-c.start}:null;}
 return doc.video?{path:doc.video,role:'video',time:t}:null;
}
function request(source,kind,doc=state().doc){return ui.api('/api/video-preview/'+encodeURIComponent(doc.id),{kind,revision:doc.revision,role:source.role,asset:source.asset,expectedPath:source.path,force:source.force===true}).catch(e=>{if(/Unknown action/i.test(e.message))throw Error('后台尚未加载本次更新，请保存草稿，彻底退出后重新启动工作台');throw e;});}
function key(source){return state().doc.id+'|'+state().doc.revision+'|'+(source.asset||source.role)+'|'+source.path;}
function pause(){sound.pause();if($('#listen').value!=='original'&&!state().exact)soundStatus.textContent='';}
async function prepare(){
 const source=descriptor(),doc=state().doc;if(!doc||state().exact)return null;
 if(!source){pause();loadedSound='';soundStatus.textContent=doc.composition?'当前画面为图片或空白，没有原视频声音':'';return null;}
 const id=key(source);if(loadingSound===id)return audioCache.get(id);const token=++soundToken;loadingSound=id;readySound=false;soundStatus.textContent='正在准备原视频声音…';
 if(!audioCache.has(id))audioCache.set(id,request(source,'audio').catch(e=>({available:false,message:e.message})));
 const result=await audioCache.get(id);if(loadingSound===id)loadingSound='';if(closed||token!==soundToken||!state().doc||key(descriptor()||{})!==id)return null;
 if(!result.available){pause();sound.removeAttribute('src');sound.load();loadedSound=id;soundStatus.textContent=result.message||'原视频没有可试听音轨';return result;}
 if(loadedSound!==id){if(sound.src!==new URL(result.url,location.href).href){pause();sound.src=result.url;sound.load();}loadedSound=id;}
 readySound=true;soundStatus.textContent='原声监听已就绪 · 不影响成片混音';return result;
}
function sync(t,playing,force=false){
 if(closed||state().exact||$('#listen').value!=='original'){pause();return;}
 const source=descriptor(t);if(!source){pause();return;}const id=key(source);
 if(loadedSound!==id){pause();if(loadingSound!==id)prepare().catch(e=>{soundStatus.textContent=e.message;});return;}
 if(!readySound||!sound.src)return;
 sound.volume=Number($('#volume').value);if(sound.readyState>=1&&(force||Math.abs(sound.currentTime-source.time)>.12))try{sound.currentTime=Math.max(0,source.time);}catch{}
 if(playing&&sound.paused)sound.play().catch(e=>{if(e.name!=='AbortError')soundStatus.textContent='原声无法播放，请重新应用视频路径或配置 FFmpeg';});if(!playing)sound.pause();
}
function status(role,text,error=false){const out=$('#apply'+(role==='video'?'Video':'Audio')+'Status');out.textContent=text;out.classList.toggle('error',error);}
async function previewVideo(force=false){
 const s=state(),doc=s.doc;if(!doc||doc.composition||!doc.video||s.exact)return;
 if(!force&&!/\.(mkv|avi)$/i.test(doc.video))return;
 const source={role:'video',path:doc.video,force},id=key(source);if(proxyKey===id){if(proxyURL&&ui.player.src!==proxyURL){ui.player.src=proxyURL;ui.player.load();return;}if(force){status('video','兼容副本仍无法网页播放，请使用准确区间预览',true);$('#noMedia').textContent='网页播放失败，请使用准确区间预览';}return;}
 const token=++proxyToken;status('video','正在准备网页兼容预览，原文件保留…');
 if(!videoCache.has(id))videoCache.set(id,request(source,'video'));
 try{const result=await videoCache.get(id);if(closed||token!==proxyToken||!state().doc||key({role:'video',path:state().doc.video})!==id)return;
  if(result.proxy){proxyKey=id;proxyURL=new URL(result.url,location.href).href;if(ui.player.src!==proxyURL){ui.player.src=proxyURL;ui.player.load();}}else if(force)throw Error('浏览器仍无法播放，请使用准确区间预览');
  status('video',result.proxy?'已加载网页兼容副本（保留音轨）；导出使用原视频':'已加载原视频');
 }catch(e){if(token===proxyToken){status('video','路径已保存；网页预览失败：'+e.message,true);$('#noMedia').textContent='无法直接播放；请检查 FFmpeg，或使用准确区间预览';}}
}
async function apply(role){
 if(!state().doc)return;const button=$('#apply'+(role==='video'?'Video':'Audio'));if(button.disabled)return;button.disabled=true;status(role,'正在应用路径并保存当前草稿…');
 try{ui.stop();await ui.save();ui.reloadSources();proxyKey='';if(role==='video'){
   if(!state().doc.audio)$('#listen').value='original';
   if(state().doc.composition)status(role,'已应用对时参考视频；画面片段请从媒体库添加，现有剪辑保持原样');
   else{status(role,'路径已应用，播放器已重新加载');await previewVideo();}
  }else status(role,'混音路径已应用并加载');schedule();
 }catch(e){status(role,e.message,true);ui.message(e.message);}finally{button.disabled=false;}
}
for(const [role,label] of [['video','视频'],['audio','混音']]){
 const input=$('#'+role),row=document.createElement('div');row.className='monitor-source-actions';row.innerHTML=`<button type="button" class="quiet" id="apply${role==='video'?'Video':'Audio'}" title="保存当前草稿，并应用${label}路径">应用并加载</button><small id="apply${role==='video'?'Video':'Audio'}Status" role="status">粘贴路径后按回车，或点击应用；支持带引号的路径。</small>`;
 input.closest('label').append(row);row.querySelector('button').onclick=()=>apply(role);
 input.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.isComposing){e.preventDefault();e.stopPropagation();apply(role);}});
}
function wave(source){
 const id=key(source);if(!waveCache.has(id)){
  const entry={loading:true},doc={id:state().doc.id,revision:state().doc.revision};waveCache.set(id,entry);
  waveQueue.push({source,doc,entry});drainWaves();
 }
 return waveCache.get(id);
}
function drainWaves(){while(waveRunning<2&&waveQueue.length){const task=waveQueue.shift();if(closed||state().doc?.id!==task.doc.id||state().doc?.revision!==task.doc.revision){Object.assign(task.entry,{loading:false,available:false,message:'素材版本已更新'});continue;}waveRunning++;request(task.source,'waveform',task.doc).then(data=>Object.assign(task.entry,data,{loading:false})).catch(e=>Object.assign(task.entry,{loading:false,available:false,message:e.message})).finally(()=>{waveRunning--;schedule();drainWaves();});}}
function pathFor(data,duration,start=0,begin=0,length=Infinity){
 if(!data?.available||!data.peaks?.length)return '';
 const end=Math.min(data.duration,begin+length),points=[];
 for(let i=0;i<data.peaks.length;i++){const source=i*data.step;if(source<begin||source>end)continue;const x=(start+source-begin)/duration*1000;if(x<0||x>1000)continue;points.push([x,Math.max(.003,data.peaks[i])*24]);}
 if(!points.length)return '';return 'M'+points.map(([x,y])=>x.toFixed(3)+','+(28-y).toFixed(2)).join(' L')+' L'+points.slice().reverse().map(([x,y])=>x.toFixed(3)+','+(28+y).toFixed(2)).join(' L')+' Z';
}
function svg(paths){return '<svg viewBox="0 0 1000 56" preserveAspectRatio="none" aria-hidden="true">'+paths.map(d=>'<path d="'+d+'"/>').join('')+'</svg>';}
function lane(kind,label,content){return `<div class="monitor-lane monitor-${kind}" data-monitor-lane="${kind}"><span class="monitor-lane-label">${label}</span>${content}</div>`;}
function paintCanvas(canvas,duration,picture=false){
 const doc=state().doc;if(!doc||!canvas||!duration)return;
 let root=canvas.querySelector(':scope > .monitor-lanes');if(!root){root=document.createElement('div');root.className='monitor-lanes';canvas.append(root);}
 const output=[];
 if(prefs.picture&&!picture&&doc.composition)output.push(lane('picture','画面',doc.composition.clips.map(c=>{const a=doc.composition.assets.find(a=>a.id===c.asset);return `<span class="monitor-picture-clip" style="left:${c.start/duration*100}%;width:${c.duration/duration*100}%">${esc(a?.name||'画面')}</span>`;}).join('')));
 if(prefs.mix&&doc.audio){const data=wave({role:'audio',path:doc.audio});output.push(lane('mix','混音 · '+esc(doc.audio.split(/[\\/]/).pop()),data.loading?'<small>正在生成波形…</small>':data.available?svg([pathFor(data,duration,doc.audioOffset)]):'<small>'+esc(data.message||'无音轨')+'</small>'));}
 if(prefs.source){const clips=doc.composition?window.CWPictureEdits.segments(doc.composition).map(({start,end,clip:c})=>({...c,start,duration:end-start,in:c.in+Math.max(0,start-c.start),assetInfo:doc.composition.assets.find(a=>a.id===c.asset)})).filter(c=>c.assetInfo?.kind==='video'):doc.video?[{start:0,in:0,duration,assetInfo:{path:doc.video,role:'video'}}]:[];
  const paths=[];let loading=false,unavailable='';for(const c of clips){const a=c.assetInfo,data=wave({path:a.path,...(a.role?{role:a.role}:{asset:a.id})});loading||=data.loading;unavailable=data.message||unavailable;if(data.available)paths.push(pathFor(data,duration,c.start,c.in,c.duration));}
  output.push(lane('source','原视频声音',paths.length?svg(paths):'<small>'+esc(loading?'正在生成波形…':unavailable||'当前没有视频音轨')+'</small>'));
 }
 const text=output.join('');if(root._monitorMarkup!==text){root._monitorMarkup=text;root.innerHTML=text;}
 root.onclick=e=>{if(e.target.closest('.monitor-lane-label'))return;const box=root.getBoundingClientRect();ui.seek(Math.max(0,Math.min(duration,(e.clientX-box.left)/box.width*duration)));};
}
function render(){
 scheduled=false;if(closed||!state().doc)return;
 paintCanvas($('#captionCanvas'),Number($('#captionCanvas')?.dataset.duration)||state().duration||1);
 if(state().doc.composition)paintCanvas($('#editCanvas'),state().doc.composition.duration,true);
}
function schedule(){if(!scheduled&&!closed){scheduled=true;requestAnimationFrame(render);}}
for(const id of ['captionCanvas','editCanvas'])new MutationObserver(schedule).observe($('#'+id),{childList:true});
function opened(){const doc=state().doc;if(!doc)return;if(project!==doc.id){pause();sound.removeAttribute('src');soundToken++;proxyToken++;loadedSound='';loadingSound='';readySound=false;proxyKey='';project=doc.id;try{prefs={...defaults,...JSON.parse(localStorage.getItem('cw-video-tracks:'+project)||'{}')};}catch{prefs={...defaults};}paintPreferences();}if(!doc.audio&&doc.video)$('#listen').value='original';previewVideo();schedule();}
sound.addEventListener('loadedmetadata',()=>sync(state().position,window.CWVideoEdit?.active()?window.CWVideoEdit.isPlaying():!ui.player.paused,true));
ui.player.addEventListener('pause',()=>{if(!window.CWVideoEdit?.active())pause();});
window.addEventListener('cw-video-change',e=>{if(['document','open','save','history'].includes(e.detail.type))opened();if(e.detail.type==='pause')pause();if(e.detail.type==='preview'){pause();soundStatus.textContent='准确预览播放的是已渲染的成片混音，原声监听已暂停';}schedule();});
window.addEventListener('cw-workbench-exit',()=>{closed=true;soundToken++;proxyToken++;pause();});
window.CWVideoMonitor={apply,prepare,sync,pause,fallback:()=>previewVideo(true)};
ui.ready.then(opened);
})();
