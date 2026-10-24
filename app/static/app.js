'use strict';
const $=s=>document.querySelector(s), $$=s=>Array.from(document.querySelectorAll(s));
const escapeHTML=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let projects=[],bundle=null,pid='hoshi',trackId=null,rangeStart=0,span=12,selected=null,selectedFlag=null,segment=null,hitboxes=[],subtitleDraft=[],requestNumber=0;
const audio=$('#audio');
let pendingSeek=null;
function seekAudio(value){pendingSeek=value;audio.currentTime=value;if(audio.readyState>=1)pendingSeek=null}
const time=s=>{s=Math.max(0,Number(s)||0);return `${String(Math.floor(s/60)).padStart(2,'0')}:${String(Math.floor(s%60)).padStart(2,'0')}`};
const precise=s=>time(s)+'.'+String(Math.floor((s%1)*100)).padStart(2,'0');
const pitchName=p=>['C','C♯','D','D♯','E','F','F♯','G','G♯','A','A♯','B'][Math.round(p)%12]+(Math.floor(p/12)-1);
function toast(message){$('#toast').textContent=message;$('#toast').classList.add('show');clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('#toast').classList.remove('show'),3300)}
function playbackError(error){if(error.name!=='AbortError')toast(error.message)}
async function api(path,body){const r=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const data=await r.json();if(!r.ok)throw new Error(data.error||'操作失败');return data}
function activeTrack(){return bundle?.parsed.tracks.find(t=>t.id===Number(trackId))}
function noteById(id){return bundle?.parsed.notes.find(n=>n.id===id)}
function effective(n){return {...n,...bundle.state.edits[n.id],...(bundle.live?.selected?bundle.liveNotes?.[n.id]:{})}}
function currentFlags(){return bundle.flags.filter(f=>f.track===Number(trackId))}
async function loadProject(id){
 const token=++requestNumber;audio.pause();pid=id;selected=null;selectedFlag=null;segment=null;rangeStart=0;
 const b=await api('/api/project/'+id);if(token!==requestNumber)return;bundle=b;
 const tracks=b.parsed.tracks;trackId=(tracks.find(t=>/POPY主声|ROSE主声/.test(t.name))||tracks.find(t=>t.name==='主声')||tracks[0])?.id;
 $('#projectCount').textContent=projects.length;$('#projects').innerHTML=projects.map(p=>`<button class="project-item ${p.id===pid?'active':''}" data-project="${p.id}"><span class="cover ${p.id}">${p.id==='hoshi'?'星':p.id==='stella'?'S':p.id==='ray'?'r':escapeHTML(p.title.slice(0,1))}</span><span><strong>${escapeHTML(p.title)}</strong><small>${escapeHTML(p.artist)}</small></span></button>`).join('');
 $$('[data-project]').forEach(el=>el.onclick=()=>loadProject(el.dataset.project).catch(e=>toast(e.message)));
 $('#title').textContent=b.project.title;$('#crumb').textContent=b.project.title;$('#artist').textContent=b.project.artist;
 $('#projectMeta').textContent=`${({ja:'日语',zh:'中文',en:'英语'}[b.project.language]||b.project.language)} · ${time(b.project.duration)} · ${tracks.length} 条音符轨 · 原工程快照已保留`;
 $('#voiceBadge').textContent='参考声库：'+[...new Set(tracks.map(t=>t.voice).filter(Boolean))].join(' / ');
 $('#trackSelect').innerHTML=tracks.map(t=>`<option value="${t.id}">${escapeHTML(t.name)} · ${t.count} 音符${t.muted?' · 静音':''}</option>`).join('');$('#trackSelect').value=trackId;
 const roles={lead:'分离主声',vocals:'完整人声',mix:'翻唱成品'};
 $('#audioSelect').innerHTML=Object.keys(b.project.audio).map(k=>`<option value="${k}">${roles[k]||k}</option>`).join('');
 $('#audioSelect').value=b.project.audio.lead?'lead':Object.keys(b.project.audio)[0];setAudio();
 $('#duration').textContent='/ '+time(b.project.duration);subtitleDraft=structuredClone(b.state.subtitles);
 renderStats();renderFlags();renderNote();draw();renderComparison();renderLyrics();renderFiles();renderLive();
}
function setAudio(preserve=false){if(!Object.keys(bundle.project.audio).length){audio.removeAttribute('src');audio.load();$('#play').disabled=true;return}$('#play').disabled=false;const role=$('#audioSelect').value,position=preserve?audio.currentTime:rangeStart,resume=preserve&&!audio.paused;pendingSeek=position;audio.onloadedmetadata=()=>{audio.currentTime=Math.min(pendingSeek??position,audio.duration||0);pendingSeek=null;if(resume)audio.play().catch(playbackError);updateTransport();draw()};audio.src=`/media/${pid}/${role}`;audio.load()}
function renderStats(){
 const t=activeTrack(),flags=currentFlags(),done=flags.filter(f=>['confirmed','ignored'].includes(bundle.state.decisions[f.id])).length;
 const m=bundle.project.metrics;
 const entries=[['当前轨音符',t?.count||0,t?.name||'','♫'],['待检查线索',flags.length-done,`${done} / ${flags.length} 已试听确认`,'◌'],['成品综合响度',m.lufs===undefined?'—':m.lufs+' LUFS','FFmpeg EBU R128 测量','≋'],['成品真峰值',m.truePeak===undefined?'—':m.truePeak+' dBTP',m.truePeak>0?'建议检查发布编码后的峰值':'保留现有音频','⌁']];
 $('#stats').innerHTML=entries.map(([label,value,detail,icon])=>`<div class="stat"><span class="stat-icon">${icon}</span><span class="stat-label">${label}</span><strong style="${typeof value==='string'&&value.length>9?'font-size:23px':''}">${value}</strong><small>${escapeHTML(detail)}</small></div>`).join('');
}
function renderFlags(){
 const kinds=[...new Map(currentFlags().map(f=>[f.kind,f.label])).entries()];const old=$('#kindFilter').value;
 $('#kindFilter').innerHTML='<option value="all">全部类型</option>'+kinds.map(([k,v])=>`<option value="${k}">${v}</option>`).join('');$('#kindFilter').value=kinds.some(k=>k[0]===old)?old:'all';
 const kind=$('#kindFilter').value,status=$('#statusFilter').value;
 const flags=currentFlags().filter(f=>(kind==='all'||f.kind===kind)&&(status==='all'||(bundle.state.decisions[f.id]||'pending')===status));
 $('#flagCount').textContent=flags.length;$('#flagList').innerHTML=flags.length?flags.map(f=>{
  const decision=bundle.state.decisions[f.id]||'pending';return `<div class="flag-card ${selectedFlag===f.id?'selected':''}" data-flag="${f.id}" tabindex="0" role="button" aria-label="试听 ${time(f.start)} ${f.label}"><div class="flag-card-head"><span class="flag-time">${time(f.start)}</span><span class="flag-type">${f.label}</span><span class="subtle">${escapeHTML(effective(noteById(f.noteId)).lyrics)}</span></div><p>${escapeHTML(f.detail)}</p><div class="decision-row"><button data-decision="confirmed" data-id="${f.id}" class="${decision==='confirmed'?'selected':''}">需要修改</button><button data-decision="ignored" data-id="${f.id}" class="${decision==='ignored'?'selected':''}">确认正常</button>${decision!=='pending'?`<button data-decision="pending" data-id="${f.id}">重置</button>`:''}</div></div>`}).join(''):'<div class="empty">这条轨道在当前筛选下<br>没有待检查片段。</div>';
 $$('[data-flag]').forEach(el=>{el.onclick=e=>{if(e.target.closest('[data-decision]'))return;focusFlag(el.dataset.flag)};el.onkeydown=e=>{if(e.target!==el)return;if(e.key==='Enter'){e.preventDefault();focusFlag(el.dataset.flag)}}});
 $$('[data-decision]').forEach(el=>el.onclick=async e=>{e.stopPropagation();try{const r=await api(`/api/state/${pid}`,{decisions:{[el.dataset.id]:el.dataset.decision}});bundle.state=r.state;renderStats();renderFlags();draw()}catch(err){toast(err.message)}});
}
function focusFlag(id){const flag=bundle.flags.find(f=>f.id===id);if(!flag)return;trackId=flag.track;$('#trackSelect').value=trackId;selectedFlag=id;selected=flag.noteId;focusNote(noteById(selected));renderFlags();renderStats()}
function focusNote(n){if(!n)return;selected=n.id;rangeStart=Math.max(0,n.start-span*.25);segment={start:Math.max(0,n.start-1.2),end:Math.min(bundle.project.duration,n.end+1.8)};seekAudio(segment.start);renderNote();draw();updateTransport()}
function renderNote(){
 if(!selected){$('#noteDetail').innerHTML='<span class="subtle">选择音符或待检查片段，查看歌词与音高。标记不会自动修改工程。</span>';return}
 const n=effective(noteById(selected));
 $('#noteDetail').innerHTML=`<div class="note-edit-meta">${escapeHTML(activeTrack().name)} · ${precise(n.start)}—${precise(n.end)} · ${Math.round((n.end-n.start)*1000)} ms · ${pitchName(n.pitch)}${bundle.live?.selected?' · 已读取 SV 当前值':bundle.state.edits[n.id]?' · 已有修订草稿':''}</div><div class="note-edit-row"><label>歌词<input id="noteLyrics" value="${escapeHTML(n.lyrics)}"></label><label>MIDI 音高<input id="notePitch" type="number" min="0" max="127" step="1" value="${n.pitch}"></label><button id="applyLive" class="button" ${bundle.live?.selected&&bundle.liveNotes?.[n.id]?'':'disabled'}>应用并在 SV 试听</button><button id="saveNote" class="button ghost">保存修订草稿</button><button id="listenNote" class="button ghost">听参考人声</button></div><p class="subtle" style="margin:12px 0 0">实时应用由 SV 使用当前声库合成并循环播放，无需导出和重开。保存请在 SV 按 Ctrl+S。原音高曲线保留；改歌词会清除该音符旧自定义音素。</p>`;
 $('#applyLive').onclick=async()=>{const id=pid;const button=$('#applyLive');button.disabled=true;audio.pause();try{const r=await api(`/api/live/${id}`,{verb:'apply',noteId:n.id,lyrics:$('#noteLyrics').value,pitch:Number($('#notePitch').value),expected:{pitch:n.pitch,lyrics:n.lyrics},start:Math.max(0,n.start-1.2),end:Math.min(bundle.project.duration,n.end+1.8)});if(pid!==id)return;bundle.state=r.state;bundle.live=r.live;bundle.liveNotes=r.notes;renderLive();renderNote();draw();toast('已应用到 SV 副本并启动循环试听；可继续修改')}catch(e){toast(e.message);await pollLive();renderNote();if(button.isConnected)button.disabled=!bundle.live?.selected}};
 $('#saveNote').onclick=async()=>{try{const r=await api(`/api/state/${pid}`,{edit:{noteId:n.id,lyrics:$('#noteLyrics').value,pitch:Number($('#notePitch').value)}});bundle.state=r.state;renderNote();renderFiles();draw();toast('修订草稿已保存，导出 SVP 后在 SV 中试听')}catch(e){toast(e.message)}};
 $('#listenNote').onclick=()=>{seekAudio(segment?.start||Math.max(0,n.start-1));audio.play().catch(playbackError)};
}
function setupCanvas(canvas){const rect=canvas.getBoundingClientRect(),dpr=window.devicePixelRatio||1;canvas.width=Math.max(1,Math.round(rect.width*dpr));canvas.height=Math.max(1,Math.round(rect.height*dpr));const c=canvas.getContext('2d');c.scale(dpr,dpr);return[c,rect.width,rect.height]}
function draw(){
 if(!bundle)return;const ns=activeTrack()?.notes||[];const visible=ns.filter(n=>n.end>rangeStart&&n.start<rangeStart+span).map(effective);
 const low=Math.max(0,Math.min(...(visible.length?visible.map(n=>n.pitch):[60]))-2),high=Math.min(127,Math.max(...(visible.length?visible.map(n=>n.pitch):[72]))+2);const nrows=high-low+1;const canvasHeight=Math.max(300,nrows*Number($('#noteSize').value)+25);$('#piano').style.height=canvasHeight+'px';$('#piano').parentElement.style.height=Math.min(520,canvasHeight)+'px';const [c,w,h]=setupCanvas($('#piano'));const rowh=(h-25)/nrows,left=34;
 c.fillStyle='#fcfcfe';c.fillRect(0,0,w,h);c.font='10px Segoe UI';
 for(let p=low;p<=high;p++){const y=25+(high-p)*rowh;if([1,3,6,8,10].includes(p%12)){c.fillStyle='#f4f4fa';c.fillRect(left,y,w-left,rowh)}c.strokeStyle=p%12===0?'#dfe0eb':'#eeeef4';c.beginPath();c.moveTo(left,y);c.lineTo(w,y);c.stroke();if(p%12===0){c.fillStyle='#a1a4b4';c.fillText(pitchName(p),3,y+rowh*.75)}}
 const baseStep=span<=12?1:span<=24?2:4,required=span/Math.max(1,Math.floor((w-left)/50));const step=[1,2,4,8,12,24,48].find(s=>s>=Math.max(baseStep,required))||48;
 for(let s=Math.ceil(rangeStart/step)*step;s<=rangeStart+span;s+=step){const x=left+(s-rangeStart)/span*(w-left);c.strokeStyle='#e9e9f2';c.beginPath();c.moveTo(x,25);c.lineTo(x,h);c.stroke();c.fillStyle='#999caf';c.fillText(time(s),x+3,15)}
 const flagged=new Set(currentFlags().filter(f=>(bundle.state.decisions[f.id]||'pending')==='pending').map(f=>f.noteId));hitboxes=[];
 for(const n of visible){let x=left+(n.start-rangeStart)/span*(w-left),endx=left+(n.end-rangeStart)/span*(w-left),y=25+(high-n.pitch)*rowh;const xx=Math.max(left,x),width=Math.max(3,Math.min(w,endx)-xx);c.fillStyle=n.id===selected?'#5336d7':flagged.has(n.id)?'#d6a366':'#aa96e8';c.globalAlpha=n.muted?.4:.95;c.beginPath();c.roundRect(xx,y+1,width,Math.max(3,rowh-2),3);c.fill();c.globalAlpha=1;if(width>16){c.save();c.beginPath();c.rect(xx+2,y,width-4,rowh);c.clip();c.fillStyle='#fff';c.font=(Number($('#noteSize').value)>=28?'14':'12')+'px Microsoft YaHei';c.fillText(n.lyrics,xx+3,y+rowh*.76);c.restore()}hitboxes.push({x:xx,y,width,height:rowh,n})}
 const mode=$('#overlaySelect').value,cmp=bundle.project.comparison||{};
 const isLead=cmp.svReference?.scope?.includes(activeTrack()?.name);
 const overlays=isLead?[['gameSmall','#37bcb3','GAME'],['sv2Native','#4f8fdd','SV2 新提取']].filter(([key])=>mode==='both'||mode===key):[];
 c.lineWidth=1.4;for(const [key,color] of overlays){c.strokeStyle=color;for(const n of cmp[key]?.notes||[]){if(n.end<rangeStart||n.start>rangeStart+span||n.pitch<low||n.pitch>high)continue;const x=Math.max(left,left+(n.start-rangeStart)/span*(w-left)),end=Math.min(w,left+(n.end-rangeStart)/span*(w-left));c.strokeRect(x,25+(high-n.pitch)*rowh+(key==='sv2Native'?3:1),Math.max(2,end-x),Math.max(2,rowh-3))}}
 const position=auditionPosition();if(position>=rangeStart&&position<=rangeStart+span){const x=left+(position-rangeStart)/span*(w-left);c.strokeStyle='#755bff';c.lineWidth=1.5;c.beginPath();c.moveTo(x,25);c.lineTo(x,h);c.stroke();c.fillStyle='#755bff';c.beginPath();c.moveTo(x-4,25);c.lineTo(x+4,25);c.lineTo(x,31);c.fill()}
 if(segment){const sx=left+(segment.start-rangeStart)/span*(w-left),ex=left+(segment.end-rangeStart)/span*(w-left);c.fillStyle='#755bff0a';c.fillRect(Math.max(left,sx),25,Math.max(0,Math.min(w,ex)-Math.max(left,sx)),h-25);c.strokeStyle='#755bff';c.setLineDash([4,4]);for(const x of [sx,ex]){if(x>=left&&x<=w){c.beginPath();c.moveTo(x,25);c.lineTo(x,h);c.stroke()}}c.setLineDash([])}
 $('#rangeLabel').textContent=`${time(rangeStart)} — ${time(Math.min(bundle.project.duration,rangeStart+span))} · 实心：已有人工工程${overlays.length?' · '+overlays.map(([key,color,label])=>(key==='gameSmall'?'绿框':'蓝框')+'：'+label).join(' / '):''}`;
 const [wc,ww,wh]=setupCanvas($('#wave'));wc.fillStyle='#faf9ff';wc.fillRect(0,0,ww,wh);const wave=bundle.project.waveform;
 const interval=Math.max(1,Math.ceil(wave.length/ww));wc.strokeStyle='#b7a5ef';wc.lineWidth=1;
 for(let i=0;i<wave.length;i+=interval){const x=i/wave.length*ww,a=Math.min(1,wave[i]*2.2)*wh*.39;wc.beginPath();wc.moveTo(x,wh/2-a);wc.lineTo(x,wh/2+a);wc.stroke()}
 const a=rangeStart/bundle.project.duration*ww,b=Math.min(1,(rangeStart+span)/bundle.project.duration)*ww;wc.fillStyle='#755bff12';wc.fillRect(a,0,b-a,wh);wc.strokeStyle='#aa96e8';wc.strokeRect(a,.5,b-a,wh-1);wc.fillStyle='#755bff';wc.fillRect(position/bundle.project.duration*ww,0,1.5,wh);
}
function updateTransport(){$('#currentTime').textContent=precise(audio.currentTime);$('#play').textContent=audio.paused?'▶':'Ⅱ';$('#play').setAttribute('aria-label',audio.paused?'播放':'暂停')}
audio.addEventListener('timeupdate',()=>{if(segment&&audio.currentTime>=segment.end){if($('#loop').checked)seekAudio(segment.start);else{audio.pause();seekAudio(segment.end)}}updateTransport();draw()});audio.addEventListener('play',updateTransport);audio.addEventListener('pause',updateTransport);audio.addEventListener('error',()=>toast('试听音频读取失败，请检查本地服务'));
$('#play').onclick=()=>{if(audio.paused){if(!segment&&$('#loop').checked)segment={start:rangeStart,end:Math.min(bundle.project.duration,rangeStart+span)};audio.play().catch(playbackError)}else audio.pause()};
$('#audioSelect').onchange=()=>setAudio(true);
$('#trackSelect').onchange=()=>{trackId=Number($('#trackSelect').value);selected=null;selectedFlag=null;renderStats();renderFlags();renderNote();draw()};
$('#kindFilter').onchange=renderFlags;$('#statusFilter').onchange=renderFlags;
$('#spanSelect').onchange=()=>{span=Number($('#spanSelect').value);draw()};$('#backRange').onclick=()=>{rangeStart=Math.max(0,rangeStart-span*.8);draw()};$('#nextRange').onclick=()=>{rangeStart=Math.min(Math.max(0,bundle.project.duration-span),rangeStart+span*.8);draw()};
$('#overlaySelect').onchange=draw;
$('#piano').onclick=e=>{const r=e.currentTarget.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top;const box=hitboxes.find(b=>x>=b.x&&x<=b.x+b.width&&y>=b.y&&y<=b.y+b.height);if(box){focusNote(box.n);renderFlags()}else{audio.currentTime=Math.max(0,rangeStart+(x-34)/(r.width-34)*span);draw()}};
$('#wave').onclick=e=>{const r=e.currentTarget.getBoundingClientRect();const t=(e.clientX-r.left)/r.width*bundle.project.duration;rangeStart=Math.max(0,Math.min(bundle.project.duration-span,t-span/2));seekAudio(t);draw()};
window.addEventListener('resize',draw);
$$('[data-tab]').forEach(button=>button.onclick=()=>{$$('[data-tab]').forEach(x=>x.classList.toggle('active',x===button));$$('.tab-panel').forEach(x=>x.hidden=x.id!==button.dataset.tab);if(button.dataset.tab==='review')draw()});
function renderComparison(){
 const cmp=bundle.project.comparison||{};
 const definitions=[['sv2Native','SV2 Pro 2.2.1','本次原生歌声转 MIDI','在空白 SV2 工程读取二次分离主声。保存未经修正的音符与音素转录，蓝框显示本次结果。','https://dreamtonics.com/synthesizerv/'],['gameSmall','GAME small','歌声音符提取','读取同一条分离主声音频，比较边界与音高。绿色框显示模型结果。','https://github.com/openvpi/GAME'],['svAnchors','SV 歌词锚点','文本与音符对齐','按歌词读音匹配现有 SV 主声音符。省去模型下载，但时间会继承现有工程的偏差。','https://resource.dreamtonics.com/scripting/'],['whisperAlign','WhisperX / CTC','已知文本与音频对齐','使用已知歌词，不重新猜测歌词。演唱长音与和声需人工检查。','https://github.com/m-bain/whisperX']];
 let html='<div class="tool-grid">'+definitions.map(([key,name,category,desc,url])=>{const r=cmp[key];return `<article class="tool-card"><span class="badge ${r?.status==='completed'?'done':''}">${r?.status==='completed'?'已在本曲测试':r?.status==='failed'?'测试遇到限制':'等待实测'}</span><h3>${name}</h3><span class="subtle">${category}</span><p>${desc}</p>${r?`<p>${escapeHTML(r.summary||r.error||'')}<br>${r.elapsed!==undefined?`运行 ${r.elapsed.toFixed(1)} 秒 · `:''}${r.notes?`${r.notes.length} 个音符`:''}</p>`:''}<a href="${url}" target="_blank" rel="noopener" class="subtle">查看官方项目</a></article>`}).join('')+'</div>';
 html+='<div class="panel" style="margin-top:22px"><h3>对比的尺度</h3><p>已有工程包含你的人工修正、调声和分轨。下面的匹配率只表示“模型与这个工程的一致程度”，不能证明哪套结果更准确。匹配窗口：起点 ±150 ms、音高 ±0.5 半音；逐个匹配，每个参考音符最多使用一次。原唱参考轨与和声轨不参与主声匹配；ray 两位主唱的重叠部分仍可能与单声部提取冲突。</p><table class="metric-table"><thead><tr><th>方法</th><th>音符数</th><th>参考一致率</th><th>匹配音符起点偏差</th><th>测试范围</th></tr></thead><tbody>';
 for(const [key,label] of [['svReference','已有人工校正参考'],['sv2Native','SV2 本次未修正提取'],['gameSmall','GAME 本次未修正提取']]){const r=cmp[key];html+=`<tr><td>${label}</td><td>${r?.count??r?.notes?.length??'—'}</td><td>${r?.agreement!==undefined?(r.agreement*100).toFixed(1)+'%':'—'}</td><td>${r?.onsetMedianMs!==undefined?r.onsetMedianMs.toFixed(0)+' ms':'—'}</td><td>${escapeHTML(r?.scope||'尚无结果')}</td></tr>`}
 html+='</tbody></table></div>';
 if(cmp.sv2Native){const r=cmp.sv2Native,pair=r.pairwiseGAME;html+=`<div class="panel"><h3>本次 SV2 提取的原始音素</h3><p>下列记录来自新提取工程，尚未校正。日语常为假名，中文常为拼音，也可能出现显式音素；它们不能直接当作汉字歌词识别结果。点击时间试听二次分离主声。</p><p>设置：${r.settings.language==='ja'?'日语':'汉语普通话'} · 半音四舍五入开启 · 音素转录开启 · 音高转移关闭 · 多线程开启。新 SV2 与新 GAME 的匹配数 ${pair.matched}，匹配 F1 ${(pair.f1*100).toFixed(1)}%（2 × 匹配数 / 两份音符数之和；按 SV2 → GAME 顺序逐个匹配，仍为一致性指标）。</p><details><summary>展开全部 ${r.count} 个原始音符</summary><div class="native-note-list">${r.notes.map((n,i)=>`<div class="native-note-row"><button class="cue-play" data-native-note="${i}">${precise(n.start)}</button><span>${pitchName(n.pitch)}</span><span>${escapeHTML(n.lyrics)}</span><small class="subtle">${escapeHTML(n.phonemes||'')}</small></div>`).join('')}</div></details><div class="path">${escapeHTML(r.rawSVP)}</div></div>`}
 const anchors=cmp.svAnchors?.segments||[],acoustic=cmp.whisperAlign?.segments||[];
 if(anchors.length){html+='<div class="panel"><h3>同一句歌词，两种时间草稿</h3><p>分别点击 SV / CTC 时间试听。CTC 使用 SV 锚点 ±700 ms 的粗窗口，遇到长音可能提早结束；字符覆盖率与模型分数都不代表时间正确率。</p>'+(cmp.whisperAlign?.medianStartShiftMs!==undefined?`<p>CTC 与 SV 句首差异中位数：${cmp.whisperAlign.medianStartShiftMs.toFixed(0)} ms · 回退到粗窗口：${cmp.whisperAlign.fallbackLines||0} 句</p>`:'')+'<div class="alignment-list">'+anchors.map((r,i)=>{const c=acoustic[i];return `<div class="alignment-row"><strong>${String(i+1).padStart(2,'0')}</strong><div><p>${escapeHTML(r.text)}</p><div class="alignment-times"><button class="cue-play" data-alignment="${i}" data-method="svAnchors">SV ${precise(r.start)}—${precise(r.end)}</button>${c?`<button class="cue-play acoustic" data-alignment="${i}" data-method="whisperAlign">CTC ${precise(c.start)}—${precise(c.end)}</button>`:'<small class="subtle">CTC 等待结果</small>'}</div><small class="subtle">读音匹配 ${(r.coverage*100).toFixed(0)}%${c?` · CTC 字符时间覆盖 ${(c.coverage*100).toFixed(0)}% · 词表覆盖 ${(c.dictionaryCoverage*100).toFixed(0)}%${c.usedFallback?' · 声学对齐失败，保留粗窗口':''}`:''}</small></div></div>`}).join('')+'</div></div>'}
 html+='<div class="panel"><h3>目前适合怎样使用</h3><p>SV 保留为主编辑器；外部提取结果作为第二份检查线索。GAME 不识别歌词。文本对齐不能替代发音校对，覆盖率也不是准确率。规则扫描可在所有工程上立即使用，但不会自行纠正音符。</p></div>';
 $('#comparisonContent').innerHTML=html;
 $$('[data-native-note]').forEach(el=>el.onclick=()=>{const n=cmp.sv2Native.notes[Number(el.dataset.nativeNote)];$('#audioSelect').value='lead';if(!audio.src.endsWith('/lead'))setAudio();segment={start:Math.max(0,n.start-.4),end:n.end+.8};seekAudio(segment.start);audio.play().catch(playbackError)});
 $$('[data-alignment]').forEach(el=>el.onclick=()=>{const r=cmp[el.dataset.method].segments[Number(el.dataset.alignment)];segment={start:Math.max(0,r.start-.4),end:r.end+.8};seekAudio(segment.start);audio.play().catch(playbackError)});
}
$('#refreshCompare').onclick=async()=>{try{const fresh=await api('/api/project/'+pid);bundle.project.comparison=fresh.project.comparison;bundle.flags=fresh.flags;renderComparison();renderFlags();renderStats();draw();toast('已读取最新实测结果')}catch(e){toast(e.message)}};
function renderLive(){
 const s=bundle.live||{},ready=s.selected;
 $('#liveDot').classList.toggle('connected',ready);$('#liveLabel').textContent=ready?'SV 已连接 · '+(s.playback==='looping'?'循环试听中':s.playback==='playing'?'播放中':'就绪'):s.connected?'SV 已连接另一首试点曲目':'SV 实时连接未启动';
 $('#liveHint').textContent=ready?'网页应用后由 SV 当前声库播放；SV 内的歌词与音高修改会同步显示。':s.connected?'在 SV 中打开当前曲目的工作副本。':'打开本曲工作副本，在 SV 的脚本菜单启动 CoverWorkbench Live。';
 $('#livePath').textContent='SV1: '+bundle.project.working+'\nSV2: '+bundle.project.sv2Working;$('#livePause').disabled=!ready;
 const button=$('#applyLive');if(button)button.disabled=!ready||!bundle.liveNotes?.[selected];
 let disconnect=$('#liveDisconnect');if(!disconnect){disconnect=document.createElement('button');disconnect.id='liveDisconnect';disconnect.className='button ghost';disconnect.textContent='断开 SV 连接';$('#livePause').after(disconnect);disconnect.onclick=async()=>{try{await api('/api/live/'+pid,{verb:'disconnect'});await pollLive()}catch(e){toast(e.message)}}}disconnect.disabled=!ready;
}
async function pollLive(){
 if(!bundle||pollLive.busy||editorBusy)return;pollLive.busy=true;const id=pid,sequence=bundle.live?.sequence;
 try{const r=await api('/api/live/'+id);if(id!==pid||editorBusy||sequence!==bundle.live?.sequence)return;const old=JSON.stringify(bundle.liveNotes?.[selected]),connection=bundle.live?.selected;bundle.live=r.live;bundle.liveNotes=r.notes;renderLive();const edited=document.activeElement?.closest('#noteDetail');if(!edited&&(connection!==r.live.selected||old!==JSON.stringify(r.notes[selected])))renderNote();draw()}catch(e){console.warn('SV bridge',e.message)}finally{pollLive.busy=false}
}
$('#livePause').onclick=async()=>{try{await api('/api/live/'+pid,{verb:'pause'});await pollLive()}catch(e){toast(e.message)}};
const livePolling=setInterval(pollLive,1500);
window.addEventListener('cw-workbench-exit',()=>{clearInterval(livePolling);audio.pause();},{once:true});
function renderLyricTools(){
 let container=$('#lyricTools');if(!container){container=document.createElement('div');container.id='lyricTools';container.className='panel lyric-tools';$('#lyrics .lyrics-layout').before(container)}
 container.innerHTML=`<span class="eyebrow">LYRIC DESK</span><h3>下载歌词，自动整理读音</h3><p class="source-meta">优先读取 MusicLyricApp 缓存；也可搜索网易云或导入 TXT / LRC。选择歌手和版本后自动保存原文、已有译文与罗马音。没有罗马音的日语歌词生成机器读音，仍需核对汉字特殊唱法。</p><div class="source-row"><input id="lyricQuery" type="text" aria-label="歌词搜索词" value="${escapeHTML(bundle.project.title+' '+bundle.project.artist)}"><button id="searchLyrics" class="button ghost">在线搜索</button><button id="refreshLyricsCache" class="button ghost">刷新工具缓存</button><label class="button ghost">导入 TXT / LRC<input id="lyricFile" type="file" accept=".txt,.lrc" hidden></label></div><div id="lyricCandidates"></div><details><summary>粘贴原文（可含 LRC 时间）</summary><textarea id="lyricImport" aria-label="导入歌词原文" placeholder="粘贴你找到的歌词"></textarea><button id="buildLyricsText" class="button ghost">整理这份歌词</button></details><div id="lyricPackage"></div>`;
 renderCandidates(bundle.lyricCandidates||[]);renderLyricPackage();
 $('#searchLyrics').onclick=async()=>{const id=pid;const button=$('#searchLyrics');button.disabled=true;button.textContent='正在搜索…';try{const r=await api('/api/lyrics-search/'+id,{query:$('#lyricQuery').value});if(pid===id)renderCandidates(r.candidates)}catch(e){toast(e.message)}finally{if(button.isConnected){button.disabled=false;button.textContent='在线搜索'}}};
 $('#refreshLyricsCache').onclick=async()=>{try{const id=pid,b=await api('/api/project/'+id);if(pid!==id)return;bundle.lyricCandidates=b.lyricCandidates;renderCandidates(b.lyricCandidates);toast('歌词工具缓存已刷新')}catch(e){toast(e.message)}};
 $('#buildLyricsText').onclick=()=>buildLyricPackage({text:$('#lyricImport').value});
 $('#lyricFile').onchange=async e=>{const f=e.target.files[0];if(!f)return;if(f.size>200000){toast('歌词文件过大');return}const text=await f.text();$('#lyricImport').value=text;await buildLyricPackage({text})};
}
function renderCandidates(rows){
 $('#lyricCandidates').innerHTML=rows.length?rows.map(r=>`<div class="lyric-candidate"><div><strong>${escapeHTML(r.title)}</strong> · ${escapeHTML(r.artist)}<small>${escapeHTML(r.album)} · ${time(r.duration)} · ${r.cached?'歌词工具缓存':'网易云在线候选'}${r.hasRomaji?' · 已有罗马音':''}${Math.abs(r.duration-bundle.project.duration)>4?' · 时长与工程有差异，请确认版本':''}</small></div><button class="button ghost" data-lyric-key="${escapeHTML(r.key)}">下载并整理</button></div>`).join(''):'<p class="subtle">没有同名缓存。可在线搜索，或用歌词工具下载后刷新缓存。</p>';
 $$('[data-lyric-key]').forEach(b=>b.onclick=async()=>{b.disabled=true;await buildLyricPackage({key:b.dataset.lyricKey});if(b.isConnected)b.disabled=false});
}
async function buildLyricPackage(body){const id=pid;try{const result=await api('/api/lyrics-build/'+id,body);if(pid!==id)return;bundle.lyricPackage=result;renderLyricPackage();toast('已保存歌词原文与读音 TXT，可逐句核对')}catch(e){toast(e.message)}}
function renderLyricPackage(){
 const p=bundle.lyricPackage;if(!p){$('#lyricPackage').innerHTML='';return}
 $('#lyricPackage').innerHTML=`<p class="source-meta">当前：${escapeHTML(p.metadata.title)} · ${escapeHTML(p.metadata.artist)} · ${escapeHTML(p.source)} · ${p.rows.length} 行 · ${p.generatedReadings} 行机器读音<br>${escapeHTML(p.notice)}</p><div class="button-row">${p.exports.map((e,i)=>`<a class="button ${i?'ghost':''}" href="${e.url}" download>${i?'下载原文文件':'下载原文＋罗马音 TXT'}</a>`).join('')}<button class="button ghost" id="saveReadings">保存读音修订</button><button class="button ghost" id="useLyricTiming" ${p.timed?'':'disabled'}>用来源 LRC 生成字幕草稿</button></div><div class="lyric-package"><table class="reading-table"><tbody>${p.rows.map((r,i)=>`<tr><td class="original-cell">${r.start!==null?`<small class="subtle">${precise(r.start)}</small><br>`:''}${escapeHTML(r.original)}<br><span class="${r.readingSource==='machine'?'reading-machine':'subtle'}">${r.readingSource==='machine'?'机器读音，待核对':r.readingSource==='provider'?'平台罗马音，待核对':r.readingSource==='user'?'用户读音':'中文原文'}</span></td><td><input data-reading="${i}" aria-label="第 ${i+1} 行罗马音" value="${escapeHTML(r.romaji)}"><input data-translation="${i}" aria-label="第 ${i+1} 行译文" placeholder="已有译文 / 自填译文" value="${escapeHTML(r.translation)}"></td></tr>`).join('')}</tbody></table></div>`;
 $$('[data-reading]').forEach(e=>e.oninput=()=>p.rows[Number(e.dataset.reading)].romaji=e.value);$$('[data-translation]').forEach(e=>e.oninput=()=>p.rows[Number(e.dataset.translation)].translation=e.value);
 $('#saveReadings').onclick=async()=>{const id=pid;try{const r=await api('/api/lyrics-revise/'+id,{rows:p.rows});if(pid!==id)return;bundle.lyricPackage=r;renderLyricPackage();toast('读音修订已保存到新的 TXT')}catch(e){toast(e.message)}};
 $('#useLyricTiming').onclick=()=>{subtitleDraft=p.rows.filter(r=>Number.isFinite(r.start)&&r.end>r.start&&r.start<bundle.project.duration).map(r=>({start:r.start,end:Math.min(bundle.project.duration,r.end),original:r.original,translation:r.translation,reading:r.romaji,status:'source_lrc_draft'}));renderSubtitles();toast('已载入来源 LRC 时间草稿；需试听核对，与旧 CTC 对齐结果分别保留')};
}
function renderLyrics(){
 $('#lyricsRaw').textContent=bundle.project.lyricsRaw;$('#subtitleOrigin').textContent='原稿来自你自行查找和下载的歌词。新下载、整理和字幕导出均进入试点目录。';renderSubtitles();renderSubtitleChecks(bundle.subtitleChecks||[]);renderLyricTools();
}
function renderSubtitles(){
 $('#subtitleRows').innerHTML=subtitleDraft.map((r,i)=>`<tr data-cue="${i}"><td><input class="cue-time" data-field="start" type="number" min="0" step="0.01" aria-label="第 ${i+1} 句起点" value="${r.start.toFixed(2)}"><input class="cue-time" data-field="end" type="number" min="0" step="0.01" aria-label="第 ${i+1} 句终点" value="${r.end.toFixed(2)}"></td><td><textarea data-field="original" aria-label="第 ${i+1} 句原文">${escapeHTML(r.original)}</textarea></td><td><textarea data-field="translation" aria-label="第 ${i+1} 句译文">${escapeHTML(r.translation)}</textarea></td><td><button class="cue-play" data-play-cue="${i}" aria-label="试听第 ${i+1} 句">▶</button><button class="cue-delete" data-delete-cue="${i}">移除</button></td></tr>`).join('')||'<tr><td colspan="4" class="empty">暂无字幕。添加一句，或从 SV 音符生成草稿。</td></tr>';
 $$('[data-cue] [data-field]').forEach(el=>el.oninput=()=>{const row=subtitleDraft[Number(el.closest('[data-cue]').dataset.cue)];row[el.dataset.field]=['start','end'].includes(el.dataset.field)?Number(el.value):el.value;row.status='edited'});
 $$('[data-play-cue]').forEach(el=>el.onclick=()=>{const r=subtitleDraft[Number(el.dataset.playCue)];segment={start:Math.max(0,r.start-.2),end:r.end+.5};seekAudio(segment.start);audio.play().catch(playbackError)});
 $$('[data-delete-cue]').forEach(el=>el.onclick=()=>{subtitleDraft.splice(Number(el.dataset.deleteCue),1);renderSubtitles()});
}
function renderSubtitleChecks(checks){$('#subIssueCount').textContent=checks.length?`· ${checks.length} 处提示`:'';$('#subtitleChecks').innerHTML=checks.length?checks.slice(0,20).map(r=>`<div class="check-item">第 ${r.row+1} 句：${escapeHTML(r.reasons.join('；'))}</div>`).join(''):'<p class="subtle">当前保存版本未发现时间顺序、范围或阅读速度异常。发音与译文仍需人工确认。</p>'}
async function saveSubtitles(){const r=await api(`/api/state/${pid}`,{subtitles:subtitleDraft});bundle.state=r.state;renderSubtitleChecks(r.checks);return r}
$('#saveSubs').onclick=()=>saveSubtitles().then(()=>toast('字幕已保存到试点目录')).catch(e=>toast(e.message));
$('#addCue').onclick=()=>{const start=subtitleDraft.length?subtitleDraft.at(-1).end:audio.currentTime;subtitleDraft.push({start,end:start+3,original:'',translation:'',reading:'',status:'draft'});renderSubtitles()};
$('#loadAnchors').onclick=()=>{
 const anchors=bundle.project.comparison?.svAnchors?.segments;
 if(!anchors?.length){toast('本曲尚未生成歌词锚点');return}
 if(subtitleDraft.length&&!confirm('将用歌词锚点替换网页草稿；现有字幕文件保持原样。继续？'))return;
 subtitleDraft=anchors.map(r=>{const old=bundle.state.subtitles.find(s=>Math.abs(s.start-r.start)<.6&&s.original===r.text);return{start:r.start,end:r.end,original:r.text,translation:old?.translation||'',reading:r.reading||'',status:'sv_anchor_draft'}});renderSubtitles();toast('歌词锚点草稿已载入，请试听校正起止时间');
};
$('#loadCTC').onclick=()=>{
 const rows=bundle.project.comparison?.whisperAlign?.segments;
 if(!rows?.length){toast('本曲尚无已完成的声学对齐结果');return}
 if(subtitleDraft.length&&!confirm('将用声学对齐替换网页草稿；原字幕文件保持原样。继续？'))return;
 subtitleDraft=rows.map(r=>{const old=bundle.state.subtitles.find(s=>s.original===r.text);return{start:r.start,end:r.end,original:r.text,translation:old?.translation||'',reading:'',status:'ctc_draft'}});renderSubtitles();toast('声学时间草稿已载入，请试听长音、断句与句尾');
};
$('#generateSubs').onclick=()=>{
 if(subtitleDraft.length&&!confirm('将替换网页中的字幕草稿，原字幕文件保持原样。继续生成？'))return;
 const ns=(activeTrack()?.notes||[]).map(effective),groups=[];let g=[];
 for(const n of ns){if(g.length&&(n.start-g.at(-1).end>.45||n.end-g[0].start>7)){groups.push(g);g=[]}g.push(n)}if(g.length)groups.push(g);
 subtitleDraft=groups.map(g=>({start:g[0].start,end:g.at(-1).end,original:g.map(n=>n.lyrics).filter(x=>x&&!['+','-','br','sil'].includes(x)).join(bundle.project.language==='zh'?'':''),translation:'',reading:'',status:'sv_draft'}));renderSubtitles();toast('已生成音符歌词草稿，需修正断句、拼写与译文');
};
async function downloadExport(action,body={}){const r=await api(`/api/${action}/${pid}`,body);const a=document.createElement('a');a.href=r.url;a.download='';document.body.append(a);a.click();a.remove();toast('已导出到试点目录：'+r.file.split(/[\\/]/).at(-1));return r}
$('#exportSubs').onclick=async()=>{try{await saveSubtitles();await downloadExport('export-subtitles',{mode:'bilingual'})}catch(e){toast(e.message)}};
$('#reportButton').onclick=()=>downloadExport('export-report').catch(e=>toast(e.message));$('#exportSVP').onclick=()=>downloadExport('export-svp').catch(e=>toast(e.message));
function renderFiles(){const p=bundle.project;const identical=p.files.every(f=>f.sha256===f.snapshot_sha256);const m=p.metrics;
 $('#fileContent').innerHTML=`<div class="file-grid"><div class="panel"><h3>正在校对的工程</h3><div class="path">${escapeHTML(p.selectedVersion)}</div><p>${escapeHTML(p.working)}</p><span class="integrity">${identical?'✓ 初始快照与原文件校验一致':'快照校验需检查'}</span><p>未连接 SV 时可保存草稿并导出；实时校对直接在 SV 中保存。${Object.keys(bundle.state.edits).length} 个音符已有修订草稿。</p></div><div class="panel"><h3>试点文件夹</h3><div class="path">${escapeHTML(p.pilot)}</div><ul class="file-list"><li>snapshots / sv、text、daw<span>原工程和歌词字幕的完整快照</span></li><li>working / sv<span>独立工作副本，渲染目录指向 exports / audio</span></li><li>analysis、media<span>扫描、模型结果、校对记录和试听音频</span></li><li>exports / svp、subtitles、audio、reports<span>试点成果，原文件不被覆盖</span></li></ul></div></div><div class="panel"><h3>导出音频检查</h3><table class="metric-table"><tbody><tr><th>格式</th><td>${p.audio.mix?.format.sample_rate||'—'} Hz / ${p.audio.mix?.format.bits_per_raw_sample||'—'} bit / ${p.audio.mix?.format.channels||'—'} 声道</td></tr><tr><th>综合响度</th><td>${m.lufs??'—'} LUFS</td></tr><tr><th>真峰值</th><td>${m.truePeak??'—'} dBTP ${m.truePeak>0?'· 建议检查削波和有损编码后的峰值':''}</td></tr><tr><th>动态范围</th><td>${m.lra??'—'} LU</td></tr></tbody></table><p>试听副本经过采样率与位深转换，数值测量来自原始 Mixdown。已有音频未做增益、限幅或重混。</p></div><div class="panel"><h3>保留的工程版本</h3><ul class="file-list">${p.versions.map(v=>`<li>${escapeHTML(v)}${v===p.selectedVersion?' <span class="tag">当前参考</span>':''}</li>`).join('')}</ul><p>当前参考版本根据文件用途选定，未推断它一定是你的最终版本。其他版本保留在 snapshots 中。</p></div>`;
 $('#fileContent').insertAdjacentHTML('afterbegin',`<div class="panel"><h3>实时校对与保存</h3><p>启动 CoverWorkbench Live 后，网页“应用并在 SV 试听”直接修改已打开副本的歌词和基础音高；无需导出重开。当前 SV 内容请在 SV 中保存。网页导出是初始参考副本＋网页修订，不能代替保存 SV 内的其他调声、分组和曲线修改。</p><div class="path">SV2 工作副本：${escapeHTML(p.sv2Working)}</div><p>歌词原文与读音记录：working / lyrics；原文＋罗马音 TXT：exports / lyrics。新歌词不会自动覆盖已有音符歌词或旧的声学对齐结果。</p></div>`);
 if(p.dawCopy){$('#fileContent').innerHTML+=`<div class="panel"><h3>Studio One 试点副本</h3><div class="path">${escapeHTML(p.dawCopy.song)}</div><p>伴奏、外部 SVP 和 Mixdown 路径已转到试点目录。非 SV 插件状态保持原样；已验证文件结构，尚未在 Studio One 中打开试听。</p><div class="path">链接的 SVP：${escapeHTML(p.dawCopy.linkedSVP)}</div>${p.id==='stella'?'<p>本 DAW 副本继承原项目链接的 _1-studio_one.svp；网页音符对比使用 _1-studio_one_midi.svp。两份版本均保留。</p>':''}</div>`}
}
document.addEventListener('keydown',e=>{if(['INPUT','TEXTAREA','SELECT'].includes(document.activeElement.tagName)||document.activeElement.isContentEditable||$('#review').hidden)return;if(e.code==='Space'&&!e.repeat){e.preventDefault();$('#play').click()}if(e.key===']')$('#nextRange').click();if(e.key==='[')$('#backRange').click()});
async function init(){projects=await api('/api/projects');$('#projectCount').textContent=projects.length;if(!projects.length){showEmptyWorkbench();return}await loadProject(projects[0].id);
 const context=document.modelContext;if(context?.registerTool){
  const tools=[{name:'read_cover_project',description:'Read the active cover project and review counts.',inputSchema:{type:'object',properties:{},additionalProperties:false},annotations:{readOnlyHint:true},execute:async()=>({project:pid,track:trackId,flags:currentFlags().length,edits:Object.keys(bundle.state.edits).length})},
   {name:'navigate_cover_project',description:'Select one of the four pilot projects in the visible workbench.',inputSchema:{type:'object',properties:{projectId:{type:'string',enum:projects.map(p=>p.id)}},required:['projectId'],additionalProperties:false},execute:async input=>{if(!projects.some(p=>p.id===input.projectId))throw new Error('Unknown project');await loadProject(input.projectId);return{project:pid}}},
   {name:'navigate_review_fragment',description:'Select a review fragment and seek its audio without starting playback.',inputSchema:{type:'object',properties:{flagId:{type:'string'}},required:['flagId'],additionalProperties:false},execute:async input=>{if(!bundle.flags.some(f=>f.id===input.flagId))throw new Error('Unknown fragment');$('[data-tab="review"]').click();focusFlag(input.flagId);return{selectedFlag,time:audio.currentTime}}}];
  for(const tool of tools){try{await context.registerTool(tool)}catch(e){console.warn('WebMCP unavailable',e.message)}}
 }
}window.addEventListener('DOMContentLoaded',()=>init().catch(e=>{$('#title').textContent='无法读取本地工程';toast(e.message)}));
