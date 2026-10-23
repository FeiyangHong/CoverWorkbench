'use strict';
let dawScan=null,dawInfo=null,dawBusy=false,dawPresetProject='',dawScanNumber=0;
async function loadDaw(){
 const state=await api('/api/daw/status');dawInfo=state;
 $('#dawBuildHistory').innerHTML=state.builds.slice(0,10).map(b=>`<article class="daw-history"><strong>${escapeHTML(b.name)}</strong><span>${b.engine?.toUpperCase()} · ${escapeHTML(dawInfo.templates.find(t=>t.id===b.template)?.name||b.template)} · ${b.mapping.length} 条人声</span><code>${escapeHTML(b.song)}</code><div class="daw-actions"><button class="button ghost" data-copy-song="${escapeHTML(b.song)}">复制工程路径</button><button class="button ghost" data-open-song="${escapeHTML(b.song)}">在 Studio One 打开</button><button class="button ghost" data-reveal-path="${escapeHTML(b.song)}">打开所在文件夹</button></div></article>`).join('')||'<p>生成后，这里会保留对应的 Song 路径与声部分配记录。</p>';
 wireDawOpenButtons($('#dawBuildHistory'));
 $$('[data-copy-song]').forEach(b=>b.onclick=()=>navigator.clipboard.writeText(b.dataset.copySong).then(()=>toast('工程路径已复制；在 Studio One 打开')).catch(()=>toast(b.dataset.copySong)));
 const previousTemplate=$('#dawTemplate').value;
 $('#dawTemplate').innerHTML=state.templates.map(t=>`<option value="${escapeHTML(t.id)}">${escapeHTML(t.name)}</option>`).join('')||'<option value="">请先在环境设置注册模板</option>';
 if(state.templates.some(t=>t.id===previousTemplate))$('#dawTemplate').value=previousTemplate;
 $('#dawRecipe').textContent=state.templates.length?'':'此设备还没有混音模板。请打开环境设置，注册自己的 Studio One Song。';
 renderDawTemplate();
 initDawOutput();
 if(bundle&&dawPresetProject!==pid&&!$('#dawSVP').value){$('#dawSVP').value=bundle.project.working;$('#dawName').value=pid+'_mix';$('#dawAccompaniment').value=bundle.project.dawCopy?.assets?.find(a=>/\.(wav|flac)$/i.test(a.original))?.original||'';dawPresetProject=pid}
 updateDawOutput();
}
function renderDawTemplate(){
 const t=dawInfo?.templates.find(t=>t.id===$('#dawTemplate').value);if(!t)return;
 const rows=t.channels.filter(c=>c.effects.length||c.type==='AudioGroupChannel');
 $('#dawRecipe').innerHTML=(t.bundled?`<p class="work-caption">初始模板 · ${escapeHTML(t.name)}<br>需安装：${escapeHTML((t.requiredPlugins||[]).join('、'))}</p>`:'')+(t.warnings||[]).map(w=>`<p class="work-caption">${escapeHTML(w)}</p>`).join('')+rows.map(c=>`<div><strong>${escapeHTML(c.name)}</strong><span>${escapeHTML(c.effects.join(' → ')||'汇总总线')}${c.muted?' · 返回静音':''}</span><small>${escapeHTML(c.sends.map(s=>s.to+' '+s.levelDB+' dB').join(' / '))}${c.destination?' → '+escapeHTML(c.destination):''}</small></div>`).join('');
}
function invalidateDaw(){dawScanNumber++;dawScan=null;$('#dawBuild').disabled=true;$('#dawTrackRows').innerHTML='';$('#dawScanSummary').textContent='文件路径或插件版本改变后，请重新读取。'}
$('#dawInspect').onclick=async()=>{
 const b=$('#dawInspect');b.disabled=true;
 const scanNumber=++dawScanNumber;
 try{
  const response=await api('/api/daw-inspect/new',{svp:$('#dawSVP').value,engine:$('#dawEngine').value});
  if(scanNumber!==dawScanNumber)return;dawScan=response;
  $('#dawScanSummary').textContent=`${dawScan.engine.toUpperCase()} 格式 · ${dawScan.tracks.filter(t=>!t.instrumental).length} 条人声候选 · ${Number(dawScan.duration).toFixed(1)} 秒`;
  $('#dawTrackRows').innerHTML=dawScan.tracks.map(t=>`<div class="daw-track" data-daw-index="${t.index}"><label><input type="checkbox" ${t.selected?'checked':''} ${t.instrumental||!t.notes||t.muted?'disabled':''}><span><strong>${escapeHTML(t.name)}</strong><small>${t.instrumental?'参考音频，不导入插件':t.notes+' 音符'+(t.muted?' · SV 已静音':'')}${t.voice?' · '+escapeHTML(t.voice):''}</small></span></label><select aria-label="${escapeHTML(t.name)} 的效果角色" ${t.instrumental||!t.notes||t.muted?'disabled':''}>${Object.entries({lead1:'主声 1',lead2:'主声 2',lead3:'主声 3',harmony:'和声'}).map(([k,v])=>`<option value="${k}" ${t.role===k?'selected':''}>${v}</option>`).join('')}</select></div>`).join('');
  $('#dawWarnings').innerHTML=dawScan.warnings.map(w=>`<p>${escapeHTML(w)}</p>`).join('');$('#dawBuild').disabled=(!dawScan.canBuild||!dawInfo?.templates.length);
 }catch(e){toast(e.message)}finally{b.disabled=false}
};
let dawPendingBuild=null,dawConflict=null;
async function submitDawBuild(retryBody){
 if(!dawScan||dawBusy)return;dawBusy=true;$('#dawBuild').disabled=true;$('#dawBuild').textContent='正在复制素材并生成工程…';
 try{
  const tracks=$$('.daw-track').filter(row=>row.querySelector('input').checked).map(row=>({index:Number(row.dataset.dawIndex),role:row.querySelector('select').value}));
  const body=retryBody||{svp:dawScan.svp,engine:dawScan.engine,sourceSHA256:dawScan.sha256,tracks,name:$('#dawName').value,accompaniment:$('#dawAccompaniment').value,template:$('#dawTemplate').value,outputDir:$('#dawOutputDir').value,folderNaming:$('#dawFolderNaming').value};
  const response=await fetch('/api/daw-build/new',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const result=await response.json();
  if(response.status===409&&result.conflict){dawPendingBuild=body;showDawConflict(result.conflict);return}
  if(!response.ok)throw new Error(result.error||'生成失败');
  $('#dawResult').hidden=false;$('#dawResult').innerHTML=`<span class="eyebrow">SONG CREATED</span><h3>工程已经建好</h3><code>${escapeHTML(result.song)}</code><p>${result.mapping.length} 条独立人声输出 · ${result.effectPresetsPreserved} 份原效果器状态保留。</p><div class="daw-routing">${result.mapping.map(t=>`<div><b>Output ${t.output}</b><span>${escapeHTML(t.svpTrack)}</span><small>${escapeHTML(t.effects.join(' → '))}</small></div>`).join('')}</div><p>${escapeHTML(result.validation)}</p><button class="button" id="copyDawResult">复制路径，在 Studio One 打开</button>`;
  $('#copyDawResult').onclick=()=>navigator.clipboard.writeText(result.song).then(()=>toast('已复制 Song 路径')).catch(()=>toast(result.song));
  $('#dawResult').insertAdjacentHTML('beforeend',`<div class="daw-actions"><button class="button ghost" data-open-song="${escapeHTML(result.song)}">在 Studio One 打开</button><button class="button ghost" data-reveal-path="${escapeHTML(result.song)}">打开所在文件夹</button></div>`);
  wireDawOpenButtons($('#dawResult'));
  await loadDaw();toast('Studio One 工程已另存生成');
 }catch(e){toast(e.message)}finally{dawBusy=false;$('#dawBuild').disabled=(!dawScan?.canBuild||!dawInfo?.templates.length);$('#dawBuild').textContent='生成独立 Studio One 工程'}
}
$('#dawBuild').onclick=()=>submitDawBuild();
$('#dawSVP').oninput=invalidateDaw;$('#dawTemplate').onchange=renderDawTemplate;
$('#dawEngine').onchange=invalidateDaw;
$('#dawUseCurrent').onclick=()=>{if(!bundle)return;$('#dawSVP').value=bundle.project.working;$('#dawName').value=pid+'_mix';$('#dawAccompaniment').value=bundle.project.dawCopy?.assets?.find(a=>/\.(wav|flac)$/i.test(a.original))?.original||'';invalidateDaw();updateDawOutput()};
const dawTabButton=$('[data-tab="daw"]'),dawTabOld=dawTabButton.onclick;
dawTabButton.onclick=e=>{dawTabOld(e);loadDaw().catch(e=>toast(e.message))};

function dawCleanPath(value){
 let text=String(value||'').trim(),pairs={'"':'"',"'":"'",'“':'”','‘':'’'};
 while(text.length>1&&pairs[text[0]]&&text.at(-1)===pairs[text[0]])text=text.slice(1,-1).trim();
 return text;
}
let dawOutputReady=false;
function initDawOutput(){
 if(dawOutputReady||!dawInfo?.outputOptions)return;dawOutputReady=true;
 let saved;try{saved=JSON.parse(localStorage.getItem('cw.daw.output')||'null')}catch{}
 const preset=dawInfo.outputOptions.find(p=>p.id===saved?.preset);
 $('#dawOutputPreset').value=preset?.id||(saved?.path?'custom':'workbench');
 $('#dawOutputDir').value=preset?.path||saved?.path||dawInfo.outputOptions[0].path;
 $('#dawFolderNaming').value=['plain','timestamp','unique'].includes(saved?.naming)?saved.naming:'plain';
 updateDawOutput();
}
function updateDawOutput(){
 const folder=dawCleanPath($('#dawOutputDir').value),name=$('#dawName').value.trim()||'my_song_mix';
 const naming=$('#dawFolderNaming').value,suffix={plain:'',timestamp:'_日期时间',unique:'_日期时间_标识'}[naming];
 $('#dawOutputPreview').textContent=folder?`新建于 ${folder.replace(/[\\/]+$/,'')}\\${name}${suffix}\\`:'请选择输出父文件夹。';
 if(dawOutputReady)try{localStorage.setItem('cw.daw.output',JSON.stringify({preset:$('#dawOutputPreset').value,path:folder,naming}))}catch{}
}
$('#dawOutputPreset').onchange=()=>{
 const preset=dawInfo?.outputOptions.find(p=>p.id===$('#dawOutputPreset').value);
 if(preset)$('#dawOutputDir').value=preset.path;
 updateDawOutput();
};
$('#dawOutputDir').oninput=()=>{$('#dawOutputPreset').value='custom';updateDawOutput()};
$('#dawName').addEventListener('input',updateDawOutput);
$('#dawFolderNaming').onchange=updateDawOutput;
for(const id of ['dawSVP','dawAccompaniment','dawOutputDir'])$('#'+id).addEventListener('blur',()=>{
 $('#'+id).value=dawCleanPath($('#'+id).value);if(id==='dawOutputDir')updateDawOutput();
});
let dawPicker=null,dawPickerRequest=0;
async function browseDawPath(path){
 const request=++dawPickerRequest;$('#dawPickerChoose').disabled=true;$('#dawPickerUp').disabled=true;
 $('#dawPickerStatus').textContent='正在读取文件夹…';$('#dawPickerEntries').replaceChildren();
 try{
  const data=await api('/api/daw-browse/new',{path,kind:dawPicker.kind,sort:$('#dawPickerSort').value,foldersFirst:$('#dawPickerFoldersFirst').checked});
  if(request!==dawPickerRequest||!dawPicker)return;
  dawPicker.path=data.path;dawPicker.parent=data.parent;$('#dawPickerPath').value=data.path;
  $('#dawPickerUp').disabled=!data.parent;$('#dawPickerChoose').disabled=false;
  $('#dawPickerStatus').textContent=data.truncated?'文件较多，仅显示前 1500 项；可以输入更具体的路径。':`${data.entries.length} 个文件夹 / 可选文件`;
  const shortcuts=[...data.roots.map(path=>({name:path,path})),...(dawInfo?.outputOptions||[])];
  $('#dawPickerShortcuts').innerHTML=shortcuts.map((p,i)=>`<button type="button" class="button ghost" data-shortcut="${i}">${escapeHTML(p.name)}</button>`).join('');
  $$('[data-shortcut]').forEach(b=>b.onclick=()=>browseDawPath(shortcuts[Number(b.dataset.shortcut)].path));
  $('#dawPickerEntries').innerHTML=data.entries.map((f,i)=>`<button type="button" class="daw-file-entry ${f.directory?'is-folder':''}" data-file-index="${i}"><span class="daw-file-kind">${f.directory?'DIR':escapeHTML(f.name.split('.').pop().toUpperCase())}</span><span>${escapeHTML(f.name)}<small>${new Date((data.sort.startsWith('created')?f.created:f.modified)*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})}${f.size!==null?' · '+dawFileSize(f.size):''}</small></span><small>${f.directory?'打开':'选择'}</small></button>`).join('')||'<p class="daw-empty">这个文件夹内没有符合类型的文件。可以前往其他文件夹。</p>';
  $$('[data-file-index]').forEach(b=>b.onclick=()=>{const f=data.entries[Number(b.dataset.fileIndex)];if(f.directory)browseDawPath(f.path);else chooseDawPath(f.path)});
 }catch(e){if(request===dawPickerRequest)$('#dawPickerStatus').textContent=e.message}
}
function chooseDawPath(path){
 const target=$('#'+dawPicker.target);target.value=path;target.dispatchEvent(new Event('input',{bubbles:true}));
 closeDawPicker();target.focus();
}
function closeDawPicker(){dawPickerRequest++;dawPicker=null;$('#dawFilePicker').close()}
$$('[data-daw-browse]').forEach(b=>b.onclick=()=>{
 dawPicker={kind:b.dataset.dawBrowse,target:b.dataset.target};
 let prefs;try{prefs=JSON.parse(localStorage.getItem('cw.daw.browse')||'null')}catch{}
 if(prefs){$('#dawPickerSort').value=prefs.sort||'modified-desc';if(!$('#dawPickerSort').value)$('#dawPickerSort').value='modified-desc';$('#dawPickerFoldersFirst').checked=prefs.foldersFirst!==false}
 $('#dawPickerTitle').textContent={project:'选择 SVP / Song 工程',audio:'选择伴奏音频',folder:'选择输出父文件夹'}[dawPicker.kind];
 $('#dawPickerChoose').hidden=dawPicker.kind!=='folder';
 $('#dawPickerHint').textContent=dawPicker.kind==='folder'?'进入目标文件夹后，点击「使用此文件夹」。':'点击文件夹进入，点击文件完成选择。文件保持在本机。';
 $('#dawFilePicker').showModal();browseDawPath($('#'+dawPicker.target).value||$('#dawSVP').value||dawInfo?.outputOptions?.[0]?.path||'');
});
$('#dawPickerNavigate').onsubmit=e=>{e.preventDefault();browseDawPath($('#dawPickerPath').value)};
$('#dawPickerClose').onclick=closeDawPicker;
$('#dawFilePicker').addEventListener('cancel',()=>{dawPickerRequest++;dawPicker=null});
$('#dawPickerUp').onclick=()=>{if(dawPicker?.parent)browseDawPath(dawPicker.parent)};
$('#dawPickerChoose').onclick=()=>{if(dawPicker?.path)chooseDawPath(dawPicker.path)};

function dawFileSize(size){return size>=1048576?(size/1048576).toFixed(1)+' MB':size>=1024?(size/1024).toFixed(1)+' KB':size+' B'}
async function openDawLocal(path,action){
 try{await api('/api/daw-open/new',{path,action});toast(action==='song'?'已请求 Studio One 打开工程':'已请求文件管理器打开位置');return true}catch(e){toast(e.message);return false}
}
function wireDawOpenButtons(root){
 root.querySelectorAll('[data-open-song]').forEach(b=>b.onclick=()=>openDawLocal(b.dataset.openSong,'song'));
 root.querySelectorAll('[data-reveal-path]').forEach(b=>b.onclick=()=>openDawLocal(b.dataset.revealPath,'folder'));
}
function showDawConflict(detail){
 dawConflict=detail;$('#dawConflictFolder').textContent=detail.folder;
 $('#dawConflictSongs').innerHTML=detail.songs.map(p=>`<option value="${escapeHTML(p)}">${escapeHTML(p.split(/[\\/]/).pop())}</option>`).join('')||'<option value="">没有找到可直接打开的 Song 文件</option>';
 $('#dawConflictOpen').disabled=!detail.songs.length;$('#dawConflictSongs').disabled=!detail.songs.length;
 $('#dawConflictDialog').showModal();
}
$('#dawConflictOpen').onclick=async()=>{if(await openDawLocal($('#dawConflictSongs').value,'song'))$('#dawConflictDialog').close()};
$('#dawConflictVersion').onclick=()=>{const body={...dawPendingBuild,conflictAction:'version'};$('#dawConflictDialog').close();submitDawBuild(body)};
$('#dawConflictReveal').onclick=()=>openDawLocal(dawConflict.folder,'folder');
$('#dawConflictCancel').onclick=()=>$('#dawConflictDialog').close();
$('#dawRevealSource').onclick=()=>openDawLocal($('#dawSVP').value,'folder');
$('#dawRevealOutput').onclick=()=>openDawLocal($('#dawOutputDir').value,'folder');
$('#dawPickerReveal').onclick=()=>{if(dawPicker?.path)openDawLocal(dawPicker.path,'folder')};
function changeDawSort(){
 try{localStorage.setItem('cw.daw.browse',JSON.stringify({sort:$('#dawPickerSort').value,foldersFirst:$('#dawPickerFoldersFirst').checked}))}catch{}
 if(dawPicker?.path)browseDawPath(dawPicker.path);
}
$('#dawPickerSort').onchange=changeDawSort;$('#dawPickerFoldersFirst').onchange=changeDawSort;
