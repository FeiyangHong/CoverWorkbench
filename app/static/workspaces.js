/* Owned project folders and finite separation jobs; idle pages do not poll. */
(() => {
'use strict';
const $=s=>document.querySelector(s),esc=v=>escapeHTML(String(v??''));
let workspace=null,capabilities=null,timer=null,serial=0,exited=false,seen=new Set(),inputProject=null,defaultRequest=0,preparingInput=false,engineTouched=false,capabilityRequest=0;
let starterFolder=null,starterRequest=0,jobBusy=false;
let inferenceTouched=false,defaultsApplied=false,modelSelections={};
const names={source:'原歌曲',vocals:'完整人声',lead:'主声',harmony:'和声',accompaniment:'伴奏'};
function current(){return bundle?.project?.id===pid?pid:null;}
function picker(id,kind){dawPicker={kind,target:id};$('#dawPickerTitle').textContent=kind==='folder'?'选择 MSST 安装目录':'选择音频';$('#dawPickerChoose').hidden=kind!=='folder';$('#dawPickerHint').textContent='在本机选择文件或文件夹。';$('#dawFilePicker').showModal();browseDawPath($('#'+id).value||'');}
async function copy(value){try{await navigator.clipboard.writeText(value);toast('路径已复制');}catch{toast(value);}}
function paint(){
 const managed=!!workspace?.managed;
 $('#workspaceRoot').textContent=workspace?.root||'';
 $('#workspaceSummary').textContent=managed?'新分离、歌词、混音工程和本曲视频的后续输出集中在这里。':'现有工程保留原样。启用统一目录后，后续工具输出会集中保存。';
 $('#workspacePrepare').hidden=managed;$('#workspacePrepare').disabled=!current();
 $('#workspaceOpen').disabled=!workspace;$('#workspaceCopy').disabled=!workspace;
 const folders=[['分离素材','separation'],['SV 保存位置','working/sv'],['Studio One','studio-one'],['歌词 / 罗马音','exports/lyrics'],['SV 音频导出','exports/audio'],['视频与成片','video']];
 $('#workspaceFolders').innerHTML=managed?folders.map(([label,folder])=>`<span><b>${label}</b><code>${folder}/</code></span>`).join(''):'';
}
async function refreshWorkspace(){const id=current(),token=++serial;workspace=null;paint();if(!id)return;try{const data=await api('/api/workspace/'+id);if(token!==serial||id!==current()||exited)return;workspace=data;paint();}catch(e){$('#workspaceSummary').textContent=e.message;}}
$('#workspacePrepare').onclick=async()=>{const id=current();if(!id)return;const name=prompt('统一项目目录名称（支持中文、日语和空格）',workspace?.suggested||'New Song');if(name===null)return;try{await api('/api/workspace/'+id,{name});await refreshWorkspace();window.dispatchEvent(new Event('cw-project-workspace-change'));toast('已建立统一目录；已有工程和视频编辑保留原样');}catch(e){toast(e.message);}};
$('#workspaceOpen').onclick=()=>workspace&&openDawLocal(workspace.root,'folder');$('#workspaceCopy').onclick=()=>workspace&&copy(workspace.root);
function memoryText(v){return Number.isFinite(v)?Math.round(v)+' MiB':'不可用';}
function selectedEngine(){return $('#separationEngine').value;}
function engineState(){return capabilities?.engines?.[selectedEngine()]||capabilities;}
function ready(){const mode=$('#separationMode').value,state=engineState();if(!state?.available)return false;if(selectedEngine()==='msst')return mode==='pipeline'?state.models.song?.available&&state.models.harmony?.available:state.models?.[mode]?.available;return (mode==='harmony'||state.models[$('#separationSongModel').value]?.available)&&(mode==='song'||state.models[$('#separationHarmonyModel').value]?.available);}
function paintEngines(){
 const state=engineState(),modern=selectedEngine()==='pymss';$('#separationEngineBadge').textContent=(modern?'PyMSS':'MSST')+' · '+(state?.available?'环境可用':'待连接');$('#separationEngineBadge').classList.toggle('ready',!!state?.available);
 $('#separationQuality').disabled=!modern;$('#separationQuality').title=modern?'重叠提高会增加推理次数，不保证分离效果单调提高':'旧 MSST 使用自己的原有配置';
 for(const id of ['separationBatchSize','separationTta','separationSaveDefaults'])$('#'+id).disabled=!modern;
 for(const [id,kind,preferred] of [['separationSongModel','song',capabilities?.defaults?.songModel||'deux'],['separationHarmonyModel','harmony',capabilities?.defaults?.harmonyModel||'bs-frazer']]){
  const select=$('#'+id),previous=modelSelections[kind]||select.value;select.disabled=!modern;
  select.innerHTML=modern?Object.entries(state?.models||{}).filter(([,m])=>m.kind===kind).map(([key,m])=>`<option value="${esc(key)}" ${m.available?'':'disabled'}>${esc(m.name)}${m.available?'':' · 未安装'}</option>`).join(''):'<option>使用旧 MSST 固定模型</option>';
  if(modern){const choices=[...select.options];select.value=choices.find(o=>o.value===previous&&!o.disabled)?.value||choices.find(o=>o.value===preferred&&!o.disabled)?.value||choices.find(o=>!o.disabled)?.value||'';modelSelections[kind]=select.value;}
 }
 $('#pymssEnvironmentSummary').textContent=modern&&state?.available?'Python：'+state.python+'；共享模型目录：'+state.installation:(state?.message||'旧 MSST 保留为备选');
 $('#separationCapability').textContent=state?.available?(modern?'PyMSS 已连接。':'旧 MSST 已连接。')+'仅使用已安装模型；任务结果和性能记录保存到本曲目录。':state?.message||'引擎不可用';
 window.dispatchEvent(new CustomEvent('cw-separation-engine-change',{detail:{engine:selectedEngine()}}));updateStart();
}
function updateStart(busy=jobBusy){jobBusy=busy;$('#separationStart').disabled=!current()||!ready()||busy||preparingInput;}
async function defaults(){const id=current(),token=++defaultRequest;preparingInput=true;updateStart();if(!id){$('#separationInput').value='';preparingInput=false;return;}try{const result=await api('/api/project-assets/'+id);if(token!==defaultRequest||id!==current())return;const role=$('#separationMode').value==='harmony'?$('#separationHarmonyInput').value:'source';$('#separationInput').value=result.assets[role]?.path||'';inputProject=id;}catch(e){toast(e.message);}finally{if(token===defaultRequest){preparingInput=false;updateStart();}}}
async function refreshJobs(){
 clearTimeout(timer);if(exited||$('#separation').hidden||document.hidden)return;
 const id=current();if(!id){$('#separationJobs').textContent='先新建一首歌或导入 SVP，再发起归属于这首歌的分离任务。';updateStart();return;}
 try{const jobs=await api('/api/separation-jobs/'+id);if(id!==current()||exited)return;
  const busy=jobs.some(j=>['queued','running'].includes(j.status));updateStart(busy);
  $('#separationJobs').innerHTML=jobs.map(j=>`<article><div><strong>${esc(j.folder.split(/[\\/]/).pop())}</strong><span class="separation-state">${esc(({queued:'准备中',running:'分离中',completed:'已完成',failed:'失败',cancelled:'已取消',interrupted:'已中断'})[j.status]||j.status)}</span></div><p>${esc(j.engine==='pymss'?String(j.message||'').replace(/\bMSST\b/g,'PyMSS'):j.message)}</p>${j.engine==='pymss'?`<small>PyMSS · ${esc(j.songModel||'')} / ${esc(j.harmonyModel||'')} · Batch ${esc(j.batchSize||1)} · TTA ${j.tta?'开启':'关闭'} · ${esc(({high:'87.5%',balanced:'50%',model:'模型默认'})[j.quality]||'')}</small>`:j.engine==='msst'?'<small>MSST · 旧版引擎</small>':'<small>历史任务 · 未记录引擎</small>'}${j.metrics?.length?`<details><summary>耗时与显存 · ${esc(j.engine||'未记录引擎')}</summary>${j.metrics.map(m=>`<p>${esc(m.model)} · 总计 ${Number(m.totalSeconds).toFixed(1)} 秒 · CUDA 分配峰值 ${memoryText(m.cudaPeakAllocatedMiB)} · 设备采样峰值 ${memoryText(m.devicePeakMemoryMiB)}（含其他软件）</p>`).join('')}</details>`:''}${Object.keys(j.outputs||{}).length?`<small>${Object.keys(j.outputs).map(k=>names[k]||k).join(' · ')}${j.skipped?.length?' · 手动路径已保留：'+j.skipped.map(k=>names[k]||k).join('、'):''}</small>`:''}<div class="stage-actions"><button class="button ghost" type="button" data-separation-folder="${esc(j.folder)}">打开结果 / 日志</button>${['queued','running'].includes(j.status)?`<button class="button ghost" type="button" data-separation-cancel="${esc(j.id)}">取消本次任务</button>`:''}</div></article>`).join('')||'<p>还没有分离任务。选择一次输入，输出路径由工作台安排。</p>';
  $('#separationJobs').querySelectorAll('[data-separation-folder]').forEach(b=>b.onclick=()=>openDawLocal(b.dataset.separationFolder,'folder'));
  $('#separationJobs').querySelectorAll('[data-separation-cancel]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{await api('/api/separation-cancel/'+id,{id:b.dataset.separationCancel});await refreshJobs();}catch(e){toast(e.message);}});
  const completed=jobs.filter(j=>j.status==='completed'&&!seen.has(j.id));jobs.forEach(j=>seen.add(j.id+':'+j.status));
  if(completed.length){completed.forEach(j=>seen.add(j.id));await refreshWorkspace();window.dispatchEvent(new Event('cw-project-assets-change'));}
  if(busy&&!$('#separation').hidden&&!document.hidden)timer=setTimeout(refreshJobs,1800);
 }catch(e){$('#separationJobs').textContent=e.message;updateStart();}
}
async function enter(){const token=++capabilityRequest;try{await refreshStarter();const first=!capabilities,data=await api('/api/separation-capabilities');if(exited||token!==capabilityRequest)return;capabilities=data;if(!defaultsApplied){defaultsApplied=true;if(!inferenceTouched){const d=data.defaults||{};modelSelections={song:d.songModel||'deux',harmony:d.harmonyModel||'bs-frazer'};$('#separationQuality').value=d.quality||'high';$('#separationBatchSize').value=String(d.batchSize||4);$('#separationTta').checked=!!d.tta;}}if(first&&!engineTouched)$('#separationEngine').value=capabilities.engine||'msst';paintEngines();if(inputProject!==current())await defaults();await refreshJobs();}catch(e){if(token===capabilityRequest)$('#separationCapability').textContent=e.message;}}
$('#separationEngine').onchange=()=>{engineTouched=true;paintEngines();api('/api/settings/new',{separationEngine:selectedEngine()}).catch(e=>toast(e.message));};
for(const [id,kind] of [['separationSongModel','song'],['separationHarmonyModel','harmony']])$('#'+id).onchange=()=>{inferenceTouched=true;modelSelections[kind]=$('#'+id).value;updateStart();};
for(const id of ['separationQuality','separationBatchSize','separationTta'])$('#'+id).onchange=()=>{inferenceTouched=true;};
$('#separationSaveDefaults').onclick=async()=>{const button=$('#separationSaveDefaults');button.disabled=true;try{const result=await api('/api/settings/new',{separationSongModel:$('#separationSongModel').value,separationHarmonyModel:$('#separationHarmonyModel').value,separationQuality:$('#separationQuality').value,separationBatchSize:$('#separationBatchSize').value,separationTta:$('#separationTta').checked?'on':'off'});$('#separationDefaultsStatus').textContent='已保存，下次打开自动使用；已有任务参数保持原样';}catch(e){$('#separationDefaultsStatus').textContent=e.message;}finally{button.disabled=selectedEngine()!=='pymss';}};
$('#pymssSettingsForm').onsubmit=async e=>{e.preventDefault();try{await api('/api/settings/new',Object.fromEntries(['pymssDirectory','pymssPython','pymssModels','pymssDataRoot'].map(k=>[k,$('#'+k).value])));$('#pymssSettingsStatus').textContent='已保存';await enter();}catch(error){$('#pymssSettingsStatus').textContent=error.message;}};
for(const key of ['pymssDirectory','pymssPython','pymssModels','pymssDataRoot']){const input=$('#'+key),span=document.createElement('span'),button=document.createElement('button');button.type='button';button.className='button ghost';button.textContent='浏览';input.replaceWith(span);span.append(input,button);button.onclick=async()=>{try{const result=await window.CWCommon.pick(key==='pymssPython'?'launcher':'folder',input.value);if(result)input.value=result;}catch(e){toast(e.message);}};}
$('#pymssPrepareModels').onclick=async e=>{e.target.disabled=true;try{const models=Object.keys(capabilities?.engines?.pymss?.models||{});await api('/api/studio-tools/new',{kind:'pymss-models',models});$('#pymssSettingsStatus').textContent='已提交后台模型准备；完成后点击刷新任务';document.querySelector('#taskCenterButton')?.click();}catch(error){$('#pymssSettingsStatus').textContent=error.message;}finally{e.target.disabled=false;}};
api('/api/settings').then(d=>{for(const k of ['pymssDirectory','pymssPython','pymssModels','pymssDataRoot'])$('#'+k).value=d.settings[k]||'';}).catch(()=>{});
$('#separationMode').onchange=()=>{$('#separationHarmonyField').hidden=$('#separationMode').value==='song';defaults();updateStart();};$('#separationHarmonyInput').onchange=()=>{if($('#separationMode').value==='harmony')defaults();};$('#separationPick').onclick=()=>picker('separationInput','audio');$('#separationRefresh').onclick=enter;
$('#separationForm').onsubmit=async e=>{e.preventDefault();const id=current();if(!id)return;$('#separationStart').disabled=true;try{await api('/api/separation-run/'+id,{engine:selectedEngine(),quality:$('#separationQuality').value,batchSize:Number($('#separationBatchSize').value),tta:$('#separationTta').checked,songModel:$('#separationSongModel').value,harmonyModel:$('#separationHarmonyModel').value,mode:$('#separationMode').value,harmonyInput:$('#separationHarmonyInput').value,input:$('#separationInput').value});await refreshWorkspace();await refreshJobs();toast('分离已开始；完成后自动登记到这首歌');}catch(error){toast(error.message);updateStart();}};
window.CWProjectWorkspace=()=>workspace;
window.addEventListener('cw-music-project-loading',()=>{serial++;defaultRequest++;starterRequest++;workspace=null;inputProject=null;starterFolder=null;preparingInput=false;jobBusy=false;$('#svStarterFolder').hidden=true;$('#svStarterStatus').textContent='';$('#svStarterRegister').checked=false;clearTimeout(timer);paint();updateStart();});
window.addEventListener('cw-music-project-change',()=>{refreshWorkspace();if(!$('#separation').hidden)enter();});
window.addEventListener('cw-workspace-change',e=>{clearTimeout(timer);if(e.detail.tab==='separation')enter();if(e.detail.tab==='workflow')refreshWorkspace();});
window.addEventListener('cw-project-workspace-change',refreshWorkspace);
async function refreshStarter(){const id=current(),token=++starterRequest;$('#svStarterSubmit').disabled=true;$('#svStarterSources').replaceChildren();if(!id)return;try{const data=await api('/api/project-assets/'+id);if(token!==starterRequest||id!==current()||exited)return;const preferred=data.assets.lead?.exists?'lead':data.assets.vocals?.exists?'vocals':'source';for(const [role,label] of Object.entries(names)){const item=data.assets[role];const supported=item?.exists&&/\.(wav|flac)$/i.test(item.path);const row=document.createElement('label');row.innerHTML=`<input type="checkbox" value="${role}" ${supported?'':'disabled'} ${supported&&(role===preferred||role==='accompaniment')?'checked':''}> ${esc(label)} <small>${esc(supported?item.path:'尚未登记 WAV / FLAC')}</small>`;$('#svStarterSources').append(row);}$('#svStarterSubmit').disabled=!Object.values(data.assets).some(v=>v.exists&&/\.(wav|flac)$/i.test(v.path));}catch(e){$('#svStarterStatus').textContent=e.message;}}
$('#svStarterRefresh').onclick=refreshStarter;$('#svStarterFolder').onclick=()=>starterFolder&&openDawLocal(starterFolder,'folder');
$('#svStarterForm').onsubmit=async e=>{e.preventDefault();const id=current();if(!id)return;$('#svStarterSubmit').disabled=true;$('#svStarterStatus').textContent='正在复制素材并建立新的 SVP…';try{const result=await api('/api/sv-starter/'+id,{engine:$('#svStarterEngine').value,bpm:Number($('#svStarterBpm').value),roles:[...document.querySelectorAll('#svStarterSources input:checked')].map(c=>c.value),register:$('#svStarterRegister').checked});if(id!==current())return;starterFolder=result.folder;$('#svStarterFolder').hidden=false;$('#svStarterStatus').textContent=result.message+'\n'+result.svp+(result.skipped?.length?'\n当前 SVP 路径已在其他窗口改变，保留了那次选择。':'');window.dispatchEvent(new Event('cw-project-assets-change'));}catch(error){if(id===current())$('#svStarterStatus').textContent=error.message;}finally{if(id===current())$('#svStarterSubmit').disabled=false;}};
window.addEventListener('cw-project-assets-change',()=>{if(!$('#separation').hidden)refreshStarter();});
document.addEventListener('visibilitychange',()=>{clearTimeout(timer);if(!document.hidden&&!$('#separation').hidden)refreshJobs();});
window.addEventListener('cw-workbench-exit',()=>{exited=true;serial++;clearTimeout(timer);});
refreshWorkspace();updateStart();if(!$('#separation').hidden)enter();
})();
