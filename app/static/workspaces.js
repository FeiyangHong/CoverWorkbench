/* Owned project folders and finite MSST jobs; idle pages do not poll. */
(() => {
'use strict';
const $=s=>document.querySelector(s),esc=v=>escapeHTML(String(v??''));
let workspace=null,capabilities=null,timer=null,serial=0,exited=false,seen=new Set(),inputProject=null,defaultRequest=0,preparingInput=false;
let starterFolder=null,starterRequest=0,jobBusy=false;
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
function ready(){const mode=$('#separationMode').value,models=capabilities?.models;return capabilities?.available&&(mode==='pipeline'?models.song?.available&&models.harmony?.available:models?.[mode]?.available);}
function updateStart(busy=jobBusy){jobBusy=busy;$('#separationStart').disabled=!current()||!ready()||busy||preparingInput;}
async function defaults(){const id=current(),token=++defaultRequest;preparingInput=true;updateStart();if(!id){$('#separationInput').value='';preparingInput=false;return;}try{const result=await api('/api/project-assets/'+id);if(token!==defaultRequest||id!==current())return;const role=$('#separationMode').value==='harmony'?$('#separationHarmonyInput').value:'source';$('#separationInput').value=result.assets[role]?.path||'';inputProject=id;}catch(e){toast(e.message);}finally{if(token===defaultRequest){preparingInput=false;updateStart();}}}
async function refreshJobs(){
 clearTimeout(timer);if(exited||$('#separation').hidden||document.hidden)return;
 const id=current();if(!id){$('#separationJobs').textContent='先新建一首歌或导入 SVP，再发起归属于这首歌的分离任务。';updateStart();return;}
 try{const jobs=await api('/api/separation-jobs/'+id);if(id!==current()||exited)return;
  const busy=jobs.some(j=>['queued','running'].includes(j.status));updateStart(busy);
  $('#separationJobs').innerHTML=jobs.map(j=>`<article><div><strong>${esc(j.folder.split(/[\\/]/).pop())}</strong><span class="separation-state">${esc(({queued:'准备中',running:'分离中',completed:'已完成',failed:'失败',cancelled:'已取消',interrupted:'已中断'})[j.status]||j.status)}</span></div><p>${esc(j.message)}</p>${Object.keys(j.outputs||{}).length?`<small>${Object.keys(j.outputs).map(k=>names[k]||k).join(' · ')}${j.skipped?.length?' · 手动路径已保留：'+j.skipped.map(k=>names[k]||k).join('、'):''}</small>`:''}<div class="stage-actions"><button class="button ghost" type="button" data-separation-folder="${esc(j.folder)}">打开结果 / 日志</button>${['queued','running'].includes(j.status)?`<button class="button ghost" type="button" data-separation-cancel="${esc(j.id)}">取消本次任务</button>`:''}</div></article>`).join('')||'<p>还没有分离任务。选择一次输入，输出路径由工作台安排。</p>';
  $('#separationJobs').querySelectorAll('[data-separation-folder]').forEach(b=>b.onclick=()=>openDawLocal(b.dataset.separationFolder,'folder'));
  $('#separationJobs').querySelectorAll('[data-separation-cancel]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{await api('/api/separation-cancel/'+id,{id:b.dataset.separationCancel});await refreshJobs();}catch(e){toast(e.message);}});
  const completed=jobs.filter(j=>j.status==='completed'&&!seen.has(j.id));jobs.forEach(j=>seen.add(j.id+':'+j.status));
  if(completed.length){completed.forEach(j=>seen.add(j.id));await refreshWorkspace();window.dispatchEvent(new Event('cw-project-assets-change'));}
  if(busy&&!$('#separation').hidden&&!document.hidden)timer=setTimeout(refreshJobs,1800);
 }catch(e){$('#separationJobs').textContent=e.message;updateStart();}
}
async function enter(){try{await refreshStarter();capabilities=await api('/api/separation-capabilities');if(exited)return;$('#separationCapability').textContent=capabilities.available?'本机 MSST 运行环境已找到。'+Object.values(capabilities.models).map(m=>m.name+'：'+(m.available?'已安装':'缺少模型 / 配置')).join('；'):capabilities.message;if(inputProject!==current())await defaults();await refreshJobs();}catch(e){$('#separationCapability').textContent=e.message;}}
$('#separationMode').onchange=()=>{$('#separationHarmonyField').hidden=$('#separationMode').value==='song';defaults();updateStart();};$('#separationHarmonyInput').onchange=()=>{if($('#separationMode').value==='harmony')defaults();};$('#separationPick').onclick=()=>picker('separationInput','audio');$('#separationRefresh').onclick=enter;
$('#separationForm').onsubmit=async e=>{e.preventDefault();const id=current();if(!id)return;$('#separationStart').disabled=true;try{await api('/api/separation-run/'+id,{mode:$('#separationMode').value,harmonyInput:$('#separationHarmonyInput').value,input:$('#separationInput').value});await refreshWorkspace();await refreshJobs();toast('分离已开始；完成后自动登记到这首歌');}catch(error){toast(error.message);updateStart();}};
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
