/* Local FabFilter rendering. Audio and plugin state stay on the loopback server. */
(() => {
'use strict';
const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function request(url, body) {
 const response = await fetch(url, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
 const data = await response.json(); if (!response.ok) throw Error(data.error || '本机请求失败'); return data;
}
function seconds(value) {
 const parts=String(value).trim().split(':');
 if(parts.length>3||parts.some(p=>!/^\d+(\.\d+)?$/.test(p)))throw Error('时间请输入秒数或 mm:ss，例如 45 或 1:15.5');
 return parts.reduce((sum,p)=>sum*60+Number(p),0);
}
const clock = t => `${Math.floor(t/60)}:${(t%60).toFixed(1).padStart(4,'0')}`;
function mount(root) {
 let catalog=[], pair=null, context=null, nodes=[], playing=false, offset=0, started=0, ab='b', gains=null;
 let current='', revision=0, busy=false, alive=true, available=false, song=null;
 root.innerHTML=`<div class="mg-audio-heading"><div><span class="mg-eyebrow">YOUR VOICE · REAL PLUGINS</span><h3>用自己的声音，听真实 FabFilter。</h3></div><span class="mg-pill">本机 VST3 渲染</span></div>
 <p class="mg-audio-note">独立加载你已安装并授权的插件。A/B 使用同一人声、同一起止时间。可选单插件或工程预设模式，参数不会写入 Studio One 工程。</p>
 <p id="mgNativeEnvironment" role="status">正在检查本机插件…</p>
 <div class="mg-native-source"><label>分离人声路径<input id="mgNativePath" placeholder="粘贴 WAV / FLAC 路径，支持外层引号" autocomplete="off"></label><button id="mgNativeBrowse" class="mg-secondary">浏览文件</button><button id="mgNativeInspect" class="mg-secondary">读取音频</button></div>
 <p id="mgNativeSourceInfo" class="mg-caption">选择主唱干声更容易判断；也可以使用你从 SV 导出的人声。</p>
 <div class="mg-native-fields"><label>开始时间<input id="mgNativeStart" value="0:00" aria-label="真实试听开始时间"></label><label>结束时间<input id="mgNativeEnd" value="0:15" aria-label="真实试听结束时间"></label><label>额外尾音<select id="mgNativeTail"><option value="2">2 秒</option><option value="4" selected>4 秒</option><option value="8">8 秒</option></select></label><button id="mgNative15" class="mg-secondary">区间设为 15 秒</button><button id="mgNative30" class="mg-secondary">区间设为 30 秒</button></div>
 <div class="mg-native-fields"><label>真实插件<select id="mgNativePlugin"></select></label><label>对比方式<select id="mgNativeComparison"><option value="dry">A 干声 → B 加效果</option></select></label><label id="mgNativeShapeLabel" hidden>EQ 形状<select id="mgNativeShape"><option>Bell</option><option>High Shelf</option></select></label></div>
 <div id="mgNativeControls" class="mg-demo-controls"></div>
 <div class="mg-native-actions"><button id="mgNativeRender" class="mg-audio-play" disabled>生成真实 A/B</button><span>每段 0.25–30 秒 · 参数改变后重新生成 · 不自动播放</span></div>
 <p id="mgNativeStatus" class="mg-demo-status" role="status">请先选择人声文件和试听区间。</p>
 <div id="mgNativePlayer" hidden><div class="mg-audio-transport"><button id="mgNativePlay" class="mg-audio-play" disabled>▶ 播放</button><button id="mgNativeStop" class="mg-secondary">回到片段开头</button><div class="mg-ab-buttons" role="group" aria-label="真实插件前后对比"><button data-mg-native-ab="a" aria-pressed="false">A · 调整前</button><button data-mg-native-ab="b" aria-pressed="true">B · 调整后</button></div><label class="mg-check"><input id="mgNativeLoop" type="checkbox" checked>循环整段＋尾音</label></div>
 <div class="mg-audio-seek"><input id="mgNativeSeek" type="range" min="0" max="1" step=".01" value="0" aria-label="真实试听位置"><output id="mgNativeTime"></output></div>
 <div class="mg-audio-bottom"><label class="mg-check"><input id="mgNativeMatch" type="checkbox" checked>近似匹配 A/B 音量（RMS）</label><label class="mg-demo-volume">试听音量<input id="mgNativeVolume" type="range" min="0" max=".75" step=".01" value=".35" aria-label="真实试听音量"><output>35%</output></label></div><p id="mgNativeEvidence" class="mg-native-evidence"></p></div>
 <dialog id="mgNativePicker" class="mg-native-picker" aria-labelledby="mgNativePickerTitle"><div class="mg-audio-heading"><h3 id="mgNativePickerTitle">选择本机人声</h3><button id="mgNativePickerClose" class="mg-secondary">关闭</button></div><div id="mgNativeRoots" class="mg-native-roots"></div><form id="mgNativeNavigate" class="mg-native-source"><input id="mgNativeFolder" aria-label="音频所在文件夹" placeholder="输入文件夹路径"><button class="mg-secondary">前往</button><button id="mgNativeUp" type="button" class="mg-secondary">上一级</button></form><label class="mg-native-sort">排序<select id="mgNativeSort"><option value="modified-desc">修改时间 · 最新在前</option><option value="modified-asc">修改时间 · 最早在前</option><option value="name-asc">名称 · A → Z</option><option value="size-desc">大小 · 从大到小</option></select></label><p id="mgNativePickerStatus" role="status"></p><div id="mgNativeEntries" class="mg-native-entries"></div></dialog>`;
 const $=selector=>root.querySelector(selector), message=text=>$('#mgNativeStatus').textContent=text;
 const duration=()=>pair?.a.duration||0;
 function setAvailability(value){available=value;updateButton();}
 function updateButton(){$('#mgNativeRender').disabled=busy||!available||Boolean(song?.active()&&!song.ready);}
 function position(){const time=playing?offset+context.currentTime-started:offset;return Math.max(0,$('#mgNativeLoop').checked?time%(duration()||1):Math.min(time,duration()));}
 function cursor(){const value=position();$('#mgNativeSeek').value=value;$('#mgNativeTime').textContent=`${clock(value)} / ${clock(duration())}`;}
 function stopNodes(){for(const n of nodes){try{n.source.stop();}catch{}n.source.disconnect();n.gain.disconnect();}nodes=[];}
 function pause(){offset=position();stopNodes();playing=false;$('#mgNativePlay').textContent='▶ 播放';cursor();}
 function target(){if(!gains)return;const volume=Number($('#mgNativeVolume').value);nodes.forEach((n,i)=>n.gain.gain.setTargetAtTime(ab===(i?'b':'a')?volume*gains[i?'b':'a']:0,context.currentTime,.012));}
 function start(){if(!pair)return;root.dispatchEvent(new CustomEvent('cw-mix-play',{bubbles:true,detail:'native'}));stopNodes();const when=context.currentTime+.015;for(const key of ['a','b']){const source=context.createBufferSource(),gain=context.createGain();source.buffer=pair[key];source.loop=$('#mgNativeLoop').checked;gain.gain.value=0;source.connect(gain).connect(context.destination);source.start(when,offset%duration());nodes.push({source,gain});}started=when;playing=true;$('#mgNativePlay').textContent='Ⅱ 暂停';target();}
 function dirty(){revision++;pause();pair=null;$('#mgNativePlayer').hidden=true;$('#mgNativePlay').disabled=true;message(busy?'参数已改变，当前任务完成后请重新生成。':'设置已改变，请生成真实 A/B。');}
 function pluginControls(){const p=catalog.find(p=>p.id===$('#mgNativePlugin').value);if(!p)return;$('#mgNativeControls').innerHTML=p.controls.map(([key,label,min,max,value,step,unit])=>`<label><span>${esc(label)}<output>${value} ${esc(unit)}</output></span><input data-mg-native-control="${key}" type="range" min="${min}" max="${max}" step="${step}" value="${value}" aria-label="${esc(label)}"></label>`).join('');root.querySelectorAll('[data-mg-native-control]').forEach(input=>input.oninput=()=>{const row=p.controls.find(c=>c[0]===input.dataset.mgNativeControl);input.previousElementSibling.querySelector('output').textContent=input.value+' '+row[6];dirty();});$('#mgNativeComparison').innerHTML='<option value="dry">A 干声 → B 加效果</option>'+(p.id==='reverb'?'<option value="tail">A 3.2 秒长混响 → B 当前时间</option>':p.id==='delay'?'<option value="feedback">A 65% 长反馈 → B 当前反馈</option>':'');$('#mgNativeShapeLabel').hidden=p.id!=='eq';const q=root.querySelector('[data-mg-native-control="q"]');if(q)q.disabled=$('#mgNativeShape').value==='High Shelf';dirty();}
 async function inspect(){const data=await request('/api/mix-inspect/local',{path:$('#mgNativePath').value});$('#mgNativePath').value=data.path;$('#mgNativeSourceInfo').textContent=`${data.name} · ${clock(data.duration)} · ${data.sampleRate/1000} kHz · ${data.channels} 声道`;$('#mgNativeEnd').value=clock(Math.min(data.duration,seconds($('#mgNativeStart').value)+15));dirty();return data;}
 $('#mgNativeInspect').onclick=()=>inspect().catch(e=>message(e.message));
 $('#mgNativePath').oninput=dirty;
 for(const id of ['Start','End','Tail','Comparison','Shape'])$('#mgNative'+id).onchange=dirty;
 for(const length of [15,30])$('#mgNative'+length).onclick=()=>{try{$('#mgNativeEnd').value=clock(seconds($('#mgNativeStart').value)+length);dirty();}catch(e){message(e.message);}};
 $('#mgNativePlugin').onchange=pluginControls;
 $('#mgNativeShape').addEventListener('change',()=>{root.querySelector('[data-mg-native-control="q"]').disabled=$('#mgNativeShape').value==='High Shelf';});
 $('#mgNativeRender').onclick=async()=>{
  if(busy)return;pause();pair=null;$('#mgNativePlayer').hidden=true;const ticket=++revision;busy=true;$('#mgNativeRender').disabled=true;
  try {
   const values=Object.fromEntries([...root.querySelectorAll('[data-mg-native-control]')].map(input=>[input.dataset.mgNativeControl,Number(input.value)]));
   const payload={path:$('#mgNativePath').value,start:seconds($('#mgNativeStart').value),end:seconds($('#mgNativeEnd').value),tail:Number($('#mgNativeTail').value),plugin:$('#mgNativePlugin').value,comparison:$('#mgNativeComparison').value,shape:$('#mgNativeShape').value,values};
   const inSong=song?.active();const body=inSong?song.payload(payload):payload;message(inSong?'正在恢复工程效果器、发送与总线并渲染 A/B…':'正在本机加载真实插件并渲染…');let job=await request(inSong?'/api/mix-song-render/local':'/api/mix-render/local',body);
   while(['queued','running'].includes(job.status)){await new Promise(resolve=>setTimeout(resolve,500));if(!alive)return;job=await request('/api/mix-job/'+job.id);}
   if(job.status!=='ready')throw Error(job.error||'插件未能完成渲染');
   if(ticket!==revision){message('旧参数的渲染已完成；请按当前设置重新生成。');return;}
   if(!context)context=new AudioContext({sampleRate:48000});
   const [a,b]=await Promise.all([job.result.a,job.result.b].map(async url=>context.decodeAudioData(await (await fetch(url)).arrayBuffer())));
   if(ticket!==revision)return;
   pair={a,b};offset=0;gains=window.CWMixAudio.levels(a,b,$('#mgNativeMatch').checked);
   $('#mgNativePlayer').hidden=false;$('#mgNativePlay').disabled=false;$('#mgNativeSeek').max=a.duration;
   const r=job.result;message(`已完成 · ${r.plugin} 真实 VST3 · 原音频 ${clock(r.start)}–${clock(r.end)} ＋ ${r.tail} 秒尾音 · 48 kHz`);
   const readback=Object.entries(r.parametersB).map(([key,value])=>key+' = '+value).join(' · ');
   $('#mgNativeEvidence').textContent=`插件回读 B：${readback}。${r.comparison==='dry'?'A 为同区间干声。':'A/B 均由真实插件渲染。'}${r.plugin==='Pro-R 2'?'Space 是空间时间，实际尾音还受 Decay Rate / Decay EQ 影响。':''}基于插件默认状态试调，未加载你的 Studio One 整条混音链。切换 A/B 连续播放；回到开头返回所选片段起点。`;
   if(r.mode==='song'){$('#mgNativeEvidence').textContent=`A：已保存工程的静态设置；B：仅修改选定参数。A ${Object.entries(r.parametersA).map(([k,v])=>k+' = '+v).join(' · ')}。B ${readback}。已恢复 ${r.chainB.length} 个实际效果器及通道增益、静音、发送和总线；只播放映射的声部。${r.enableTarget?'A/B 共同启用了目标静音通道／旁通插件。':''}这是独立宿主静态混音试听，尚未与 Studio One 原生导出做抵消验证。`;if(r.differenceRms<.000001)message($('#mgNativeStatus').textContent+' · A/B 几乎相同，请确认已修改参数、素材流经目标插件，且通道／发送未静音。');}
   cursor();
  }catch(e){message(e.message);}finally{busy=false;updateButton();}
 };
 $('#mgNativePlay').onclick=async()=>{try{if(playing)pause();else{await context.resume();start();}}catch(e){message(e.message);}};
 $('#mgNativeStop').onclick=()=>{pause();offset=0;cursor();};
 $('#mgNativeSeek').oninput=()=>{const resume=playing,value=Number($('#mgNativeSeek').value);pause();offset=value;if(resume)start();cursor();};
 root.querySelectorAll('[data-mg-native-ab]').forEach(button=>button.onclick=()=>{ab=button.dataset.mgNativeAb;root.querySelectorAll('[data-mg-native-ab]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));target();});
 $('#mgNativeMatch').onchange=()=>{if(pair){gains=window.CWMixAudio.levels(pair.a,pair.b,$('#mgNativeMatch').checked);target();}};
 $('#mgNativeVolume').oninput=e=>{e.target.nextElementSibling.textContent=Math.round(Number(e.target.value)*100)+'%';target();};
 $('#mgNativeLoop').onchange=()=>nodes.forEach(n=>n.source.loop=$('#mgNativeLoop').checked);
 let parent=null, browseRevision=0, pickerKind='audio', pickerPick=null;
 async function browse(path){const ticket=++browseRevision;try{const data=await request('/api/daw-browse/local',{kind:pickerKind,path,sort:$('#mgNativeSort').value});if(ticket!==browseRevision)return;current=data.path;parent=data.parent;$('#mgNativeFolder').value=current;$('#mgNativeUp').disabled=!parent;$('#mgNativeRoots').innerHTML='';for(const path of data.roots){const b=document.createElement('button');b.textContent=path;b.className='mg-secondary';b.onclick=()=>browse(path);$('#mgNativeRoots').append(b);}$('#mgNativeEntries').innerHTML='';for(const item of data.entries){const button=document.createElement('button');button.className='mg-native-entry';const label=document.createElement('span');label.textContent=(item.directory?'📁  ':'♪  ')+item.name;const stamp=document.createElement('small');stamp.textContent=new Date(item.modified*1000).toLocaleString();button.append(label,stamp);button.onclick=()=>{if(item.directory)browse(item.path);else{$('#mgNativePicker').close();if(pickerPick)pickerPick(item.path);else{$('#mgNativePath').value=item.path;dirty();inspect().catch(e=>message(e.message));}}};$('#mgNativeEntries').append(button);}$('#mgNativePickerStatus').textContent=data.truncated?'仅显示前 1500 项，请进入更具体的文件夹。':data.entries.length+' 个文件 / 文件夹';}catch(e){$('#mgNativePickerStatus').textContent=e.message;}}
 function pick(kind,onPick,path){pickerKind=kind;pickerPick=onPick;$('#mgNativePickerTitle').textContent=kind==='song'?'选择 Studio One 工程':'选择本机音频';$('#mgNativePicker').showModal();browse(path||current);}
 $('#mgNativeBrowse').onclick=()=>pick('audio',null,$('#mgNativePath').value);
 $('#mgNativePickerClose').onclick=()=>$('#mgNativePicker').close();
 $('#mgNativeUp').onclick=()=>browse(parent);
 $('#mgNativeSort').onchange=()=>browse(current);
 $('#mgNativeNavigate').onsubmit=e=>{e.preventDefault();browse($('#mgNativeFolder').value);};
 song=window.CWSongMix?.mount(root,{dirty,ready:updateButton,pick});
 request('/api/mix-native').then(data=>{catalog=data.plugins;$('#mgNativePlugin').innerHTML=catalog.map(p=>`<option value="${p.id}" ${p.installed?'':'disabled'}>${esc(p.name)}${p.installed?'':'（未安装）'}</option>`).join('');const available=catalog.find(p=>p.installed);if(available)$('#mgNativePlugin').value=available.id;pluginControls();const enabled=Boolean(data.engine&&data.decoder&&available);setAvailability(enabled);$('#mgNativeEnvironment').textContent=!data.engine?'需安装可选试听引擎：在工作台目录运行 .\\tools\\InstallNativeAudio.ps1':!data.decoder?'请先在环境设置中配置 FFmpeg 和 FFprobe。':!available?'未检测到 FabFilter VST3，请在本机安装并授权。':`已就绪 · ${catalog.filter(p=>p.installed).map(p=>p.name.replace('FabFilter ','')).join(' / ')}`;}).catch(e=>{$('#mgNativeEnvironment').textContent=e.message;});
 function tick(){if(!alive)return;if(playing&&!$('#mgNativeLoop').checked&&offset+context.currentTime-started>=duration()){pause();offset=0;}if(pair)cursor();requestAnimationFrame(tick);}tick();window.addEventListener('pagehide',pause);
 return {pause,destroy(){alive=false;pause();context?.close();}};
}
window.CWNativeMix={mount};
})();
