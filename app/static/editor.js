'use strict';
let editorBusy=false,editorProject='',editorRibbonKey='',svGainDirty=false;
const savedVolumes=JSON.parse(localStorage.getItem('cw-volumes')||'{"reference":80,"cover":80}');
$('#referenceVolume').value=savedVolumes.reference;$('#coverVolume').value=savedVolumes.cover;
function auditionPosition(){return $('#auditionTarget').value==='sv'&&bundle?.live?.selected?bundle.live.playhead||0:audio.currentTime}
function auditionPlaying(){return $('#auditionTarget').value==='sv'?bundle?.live?.selected&&['playing','looping'].includes(bundle.live.playback):!audio.paused}
function validRange(){
 const a=Number($('#rangeA').value),b=Number($('#rangeB').value);
 if(!Number.isFinite(a)||!Number.isFinite(b)||a<0||b<=a||b>bundle.project.duration+.01||b-a>60)throw new Error('请设置有效 A–B 区间：0 ≤ A < B ≤ 歌曲时长，长度最多 60 秒');
 segment={start:a,end:b};return segment;
}
function syncRange(){if(!bundle)return;if(!segment)segment={start:0,end:Math.min(12,bundle.project.duration)};$('#rangeA').value=segment.start.toFixed(2);$('#rangeB').value=segment.end.toFixed(2);refreshEditor()}
function setRange(a,b){segment={start:Math.max(0,a),end:Math.min(bundle.project.duration,b)};syncRange();draw()}
function refreshVolumes(){const ref=Number($('#referenceVolume').value),cover=Number($('#coverVolume').value);audio.volume=($('#audioSelect').value==='mix'?cover:ref)/100;$('#referenceVolumeValue').textContent=ref+'%';$('#coverVolumeValue').textContent=cover+'%';localStorage.setItem('cw-volumes',JSON.stringify({reference:ref,cover}));$('#muteAudio').setAttribute('aria-pressed',String(audio.muted));$('#muteAudio').textContent=audio.muted?'取消网页静音':'静音网页音频'}
async function nativeCommand(body){
 if(editorBusy)throw new Error('SV 正在确认上一步，请稍候');
 editorBusy=true;refreshEditor();const id=pid;
 try{const r=await api('/api/live/'+id,body);if(id!==pid)return r;bundle.live=r.live;bundle.liveNotes=r.notes;if(r.state)bundle.state=r.state;return r}
 finally{editorBusy=false;refreshEditor();draw()}
}
async function beginAudition(restart=false){
 const r=validRange(),target=$('#auditionTarget').value;
 if(target==='sv'){
   if(!bundle.live?.selected)throw new Error('请先连接当前曲目的 SV 工作副本');
   audio.pause();const pos=auditionPosition();const from=restart||pos<r.start||pos>=r.end?r.start:pos;
   await nativeCommand({verb:'play',start:r.start,end:r.end,position:from,loop:$('#loop').checked});
 }else{
   if(bundle.live?.selected&&['playing','looping'].includes(bundle.live.playback))await nativeCommand({verb:'pause'});
   const pos=audio.currentTime;if(restart||pos<r.start||pos>=r.end)seekAudio(r.start);
   refreshVolumes();await audio.play();
 }
 refreshEditor();
}
async function pauseAudition(){if($('#auditionTarget').value==='sv')await nativeCommand({verb:'pause'});else audio.pause();refreshEditor()}
function editorAction(fn){return async()=>{try{await fn()}catch(e){toast(e.message)}}}
const baseFocusNote=focusNote;
focusNote=function(n){audio.pause();if(bundle?.live?.selected&&['playing','looping'].includes(bundle.live.playback))nativeCommand({verb:'pause'}).catch(e=>toast(e.message));baseFocusNote(n);syncRange();refreshEditor()};
const baseRenderNote=renderNote;
renderNote=function(){
 baseRenderNote();if(!selected){refreshEditor();return}
 const n=effective(noteById(selected)),apply=$('#applyLive');
 $('#noteDetail p').textContent='应用直接修改 SV 已打开副本，并按上方 A–B 区间试听。Ctrl+S 在 SV 保存；改歌词会清除该音符旧自定义音素，原音高曲线保留。';
 apply.onclick=editorAction(async()=>{
   const r=validRange();audio.pause();$('#auditionTarget').value='sv';
   const lyrics=$('#noteLyrics').value,pitch=Number($('#notePitch').value);
   await nativeCommand({verb:'apply',noteId:n.id,lyrics,pitch,expected:{pitch:n.pitch,lyrics:n.lyrics},start:r.start,end:r.end,position:r.start,loop:$('#loop').checked});
   renderNote();toast(`已应用到 SV · ${precise(r.start)}—${precise(r.end)} · ${$('#loop').checked?'循环':'单次'}试听`);
 });
 $('#listenNote').onclick=editorAction(async()=>{$('#auditionTarget').value='reference';if($('#audioSelect').value==='mix'){$('#audioSelect').value=bundle.project.audio.lead?'lead':'vocals';setAudio(true)}await beginAudition(true)});
 refreshEditor();
};
const baseRenderLive=renderLive;
renderLive=function(){baseRenderLive();refreshEditor()};
function refreshEditor(){
 if(!bundle||$('#review').hidden)return;
 if(editorProject!==pid){editorProject=pid;segment={start:0,end:Math.min(12,bundle.project.duration)};$('#rangeA').value=0;$('#rangeB').value=segment.end;$('#auditionTarget').value='reference';svGainDirty=false;editorRibbonKey=''}
 const live=bundle.live||{},native=$('#auditionTarget').value==='sv',playing=auditionPlaying();
 $('#currentTime').textContent=precise(auditionPosition());$('#play').textContent=playing?'Ⅱ':'▶';$('#play').setAttribute('aria-label',playing?'暂停':'播放');
 $('#audioSelect').disabled=native;$('#auditionTarget option[value="sv"]').disabled=!live.selected;
 for(const sel of ['#play','#restart','#stop'])$(sel).disabled=editorBusy||(native&&!live.selected);
 if($('#applyLive')){$('#applyLive').disabled=editorBusy||!live.selected||!bundle.liveNotes?.[selected];$('#applyLive').textContent='应用并在 SV 试听'}
 const a=Number($('#rangeA').value),b=Number($('#rangeB').value);
 $('#auditionSummary').textContent=`${precise(a)} → ${precise(b)} · ${(b-a).toFixed(2)} 秒 · ${$('#loop').checked?'循环播放':'播放一次'}`;
 $('#playHelp').textContent=`空格：${$('#spacePolicy').value==='resume'?'暂停后继续当前位置':'暂停后从 A 重新播放'}；↶ 从 A 重播；■ 停止回 A。当前控制：${native?'SV 实时合成':'网页音频'}。`;
 $('#voiceContext').textContent='· '+(activeTrack()?.name||'');
 $('#voiceHelp').textContent=`当前校对：${activeTrack()?.name||''}${selected?'，音符 '+effective(noteById(selected)).lyrics:''}。初始参考声库：${activeTrack()?.voice||'未记录'}（历史工程标签）。实际声库以 SV 右侧选中组为准。`;
 const track=live.tracks?.find(t=>t.track===Number(trackId));
 if(track?.gainSupported&&!svGainDirty){$('#svGain').value=track.gain;$('#svGainValue').textContent=track.gain.toFixed(1)+' dB'}
 $('#applySVGain').disabled=editorBusy||!live.selected||live.protocol!==3||!track?.gainSupported;
 if(!live.selected)$('#svGainValue').textContent='未连接';else if(!track?.gainSupported)$('#svGainValue').textContent='请在 SV 调整';
 const visible=(activeTrack()?.notes||[]).filter(n=>n.end>rangeStart&&n.start<rangeStart+span).map(effective);
 const key=JSON.stringify([pid,trackId,selected,visible.map(n=>[n.id,n.lyrics,n.pitch])]);
 if(editorRibbonKey!==key){editorRibbonKey=key;$('#lyricRibbon').innerHTML=visible.length?visible.map(n=>`<button data-readable-note="${n.id}" class="${selected===n.id?'active':''}" title="${precise(n.start)} · ${pitchName(n.pitch)}"><strong>${escapeHTML(n.lyrics||'∅')}</strong><small>${precise(n.start)} · ${pitchName(n.pitch)}</small></button>`).join(''):'<span class="subtle">当前视野没有音符，可点击整曲波形定位。</span>';$$('[data-readable-note]').forEach(b=>b.onclick=()=>focusNote(noteById(b.dataset.readableNote)))}
 refreshVolumes();
}
updateTransport=refreshEditor;
const baseDraw=draw;draw=function(){baseDraw();refreshEditor()};
$('#play').onclick=editorAction(async()=>{if(auditionPlaying())await pauseAudition();else await beginAudition($('#spacePolicy').value==='restart')});
$('#restart').onclick=editorAction(()=>beginAudition(true));
$('#stop').onclick=editorAction(async()=>{const r=validRange();if($('#auditionTarget').value==='sv')await nativeCommand({verb:'seek',start:r.start,end:r.end,position:r.start});else{audio.pause();seekAudio(r.start)}refreshEditor()});
$('#auditionTarget').onchange=editorAction(async()=>{audio.pause();if(bundle.live?.selected)await nativeCommand({verb:'pause'});refreshEditor();draw()});
$('#audioSelect').onchange=()=>{setAudio(true);refreshVolumes()};
for(const id of ['rangeA','rangeB'])$('#'+id).onchange=()=>{try{validRange();refreshEditor();draw()}catch(e){toast(e.message)}};
$('#loop').onchange=editorAction(async()=>{validRange();if(auditionPlaying()&&$('#auditionTarget').value==='sv')await beginAudition(false);refreshEditor();draw()});
$('#spacePolicy').onchange=refreshEditor;
$('#setA').onclick=()=>setRange(auditionPosition(),Math.max(auditionPosition()+.2,Number($('#rangeB').value)));
$('#setB').onclick=()=>{const b=auditionPosition();if(b<=Number($('#rangeA').value)){toast('B 必须晚于 A');return}setRange(Number($('#rangeA').value),b)};
$('#rangeNote').onclick=()=>{if(!selected){toast('请先选择音符');return}const n=effective(noteById(selected));setRange(n.start-1.2,n.end+1.8)};
$('#rangeView').onclick=()=>setRange(rangeStart,rangeStart+Math.min(span,60));
$('#rangePhrase').onclick=()=>{if(!selected){toast('请先选择音符');return}const ns=activeTrack().notes.map(effective).sort((a,b)=>a.start-b.start);let i=ns.findIndex(n=>n.id===selected),j=i;while(i>0&&ns[i].start-ns[i-1].end<.6&&ns[j].end-ns[i-1].start<15)i--;while(j<ns.length-1&&ns[j+1].start-ns[j].end<.6&&ns[j+1].end-ns[i].start<15)j++;setRange(ns[i].start-.5,ns[j].end+.8)};
for(const id of ['referenceVolume','coverVolume'])$('#'+id).oninput=refreshVolumes;
$('#muteAudio').onclick=()=>{audio.muted=!audio.muted;refreshVolumes()};
$('#svGain').oninput=()=>{svGainDirty=true;$('#svGainValue').textContent=Number($('#svGain').value).toFixed(1)+' dB（待应用）'};
$('#applySVGain').onclick=editorAction(async()=>{await nativeCommand({verb:'gain',track:Number(trackId),gain:Number($('#svGain').value)});svGainDirty=false;refreshEditor();toast('已修改 SV 副本当前轨道增益；可在 SV 撤销')});
function zoomTimeline(direction,anchor=selected?noteById(selected).start:rangeStart+span/2){const sizes=[3,6,12,24,48],i=sizes.indexOf(span);span=sizes[Math.max(0,Math.min(sizes.length-1,i+direction))];$('#spanSelect').value=span;rangeStart=Math.max(0,Math.min(bundle.project.duration-span,anchor-span/2));draw()}
$('#zoomIn').onclick=()=>zoomTimeline(-1);$('#zoomOut').onclick=()=>zoomTimeline(1);
$('#zoomNote').onclick=()=>{if(!selected){toast('请先选择音符');return}span=3;$('#spanSelect').value=span;rangeStart=Math.max(0,noteById(selected).start-1);draw()};
$('#noteSize').onchange=draw;
$('#piano').addEventListener('wheel',e=>{if(!e.ctrlKey)return;e.preventDefault();const r=e.currentTarget.getBoundingClientRect();zoomTimeline(e.deltaY<0?-1:1,rangeStart+(e.clientX-r.left)/r.width*span)},{passive:false});
async function seekAudition(t){t=Math.max(0,Math.min(bundle.project.duration,t));if($('#auditionTarget').value==='sv')await nativeCommand({verb:'seek',start:Math.max(0,t-.1),end:t+.1,position:t});else{audio.pause();seekAudio(t)}draw()}
$('#piano').onclick=e=>{const r=e.currentTarget.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top;const b=hitboxes.find(b=>x>=b.x&&x<=b.x+b.width&&y>=b.y&&y<=b.y+b.height);if(b){focusNote(b.n);renderFlags()}else seekAudition(rangeStart+(x-34)/(r.width-34)*span).catch(e=>toast(e.message))};
$('#wave').onclick=e=>{const r=e.currentTarget.getBoundingClientRect(),t=(e.clientX-r.left)/r.width*bundle.project.duration;rangeStart=Math.max(0,Math.min(bundle.project.duration-span,t-span/2));seekAudition(t).catch(e=>toast(e.message))};
window.addEventListener('resize',draw);
audio.addEventListener('timeupdate',refreshEditor);audio.addEventListener('play',refreshEditor);audio.addEventListener('pause',refreshEditor);
refreshVolumes();

audio.addEventListener('play',()=>{if($('#auditionTarget').value==='sv'){$('#auditionTarget').value='reference';if(bundle?.live?.selected)nativeCommand({verb:'pause'}).catch(e=>toast(e.message))}syncRange()});
