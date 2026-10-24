/* Native tools do the creative work; this shell handles files and handoffs. */
(() => {
'use strict';
const $=s=>document.querySelector(s),labels={source:'原歌曲',lead:'分离主声',harmony:'和声',accompaniment:'伴奏',svp:'SV 工程',song:'Studio One 工程',mix:'成品混音'};
let assets=null,link=null,request=0,assetProject=null,assetSnapshot=null,service=null,probeRequest=0,serviceTimer=null,exited=false;
window.CWLegacyEnabled=false;
const assetDialog=document.createElement('dialog');assetDialog.id='productionAssetDialog';assetDialog.className='production-dialog';assetDialog.setAttribute('aria-labelledby','productionAssetTitle');
assetDialog.innerHTML=`<form id="productionAssetForm"><div class="production-section-head"><h2 id="productionAssetTitle">工程与素材路径</h2><button type="button" class="button ghost" id="productionAssetClose">关闭</button></div><p>使用本机文件路径，支持 Windows「复制文件地址」的引号。仅登记文件，保留现有视频编辑；清空字段可恢复自动来源。</p>${Object.entries(labels).map(([key,label])=>`<label class="production-field">${label}<span><input id="productionPath_${key}" aria-label="${label}路径" data-production-path="${key}"><button type="button" class="button ghost" data-production-pick="${key}">浏览</button></span></label>`).join('')}<p id="productionAssetError" class="production-error" role="status"></p><div class="production-actions"><button class="button" type="submit">保存素材路径</button></div></form>`;
document.body.append(assetDialog);
const serviceDialog=document.createElement('dialog');serviceDialog.id='msstSettingsDialog';serviceDialog.className='production-dialog';serviceDialog.setAttribute('aria-labelledby','msstSettingsTitle');
serviceDialog.innerHTML=`<form id="msstSettingsForm"><div class="production-section-head"><h2 id="msstSettingsTitle">连接自己的 MSST</h2><button type="button" class="button ghost" id="msstSettingsClose">关闭</button></div><p>先单独安装 MSST 与模型。这些设置只保存在本机，其他设备可使用自己的安装位置。</p><label class="production-field">MSST 本机网页地址<input id="msstUrl" name="msstUrl" placeholder="http://127.0.0.1:7860" required></label><label class="production-field">启动程序或桌面快捷方式<span><input id="msstLauncher" name="msstLauncher" placeholder="MSST 的 .exe 或 .lnk 路径，可留空"><button type="button" class="button ghost" id="msstPickLauncher">浏览</button></span></label><p class="service-note">启动程序自己决定端口；若 MSST 自动换了端口，请填写它实际显示的地址。工作台不更改 MSST 配置、不安装模型。</p><p id="msstSettingsError" class="production-error" role="status"></p><div class="production-actions"><button class="button" type="submit">保存服务设置</button></div></form>`;
document.body.append(serviceDialog);
function current(){return bundle?.project?.id===pid?pid:null;}
function tab(name){$('.tabs [data-tab="'+name+'"]').click();}
function picker(target,kind,title){dawPicker={kind,target};$('#dawPickerTitle').textContent=title;$('#dawPickerChoose').hidden=true;$('#dawPickerHint').textContent='文件保留在本机，仅登记路径。';$('#dawFilePicker').showModal();browseDawPath($('#'+target).value||'');}
async function copy(text){try{await navigator.clipboard.writeText(text);toast('路径已复制');}catch{toast(text);}}
function renderAssetFiles(target,keys){
 const root=$(target);root.replaceChildren();
 for(const key of keys){const item=assets?.assets[key],row=document.createElement('div');row.className='production-file';row.innerHTML=`<span class="asset-mark ${item?.exists?'available':''}">${item?.exists?'✓':'○'}</span><div><strong>${labels[key]}</strong><small>${escapeHTML(item?.path||'尚未登记')}</small></div><div class="asset-actions">${item?.exists?`<button class="button ghost" data-copy="${key}">复制路径</button><button class="button ghost" data-reveal="${key}">定位文件</button>`:'<span>可在管理文件路径中添加</span>'}</div>`;root.append(row);}
 root.querySelectorAll('[data-copy]').forEach(b=>b.onclick=()=>copy(assets.assets[b.dataset.copy].path));
 root.querySelectorAll('[data-reveal]').forEach(b=>b.onclick=()=>openAsset(b.dataset.reveal,'folder'));
}
function paint(){
 const have=key=>!!assets?.assets[key]?.exists;
 $('#productionSVState').textContent=have('svp')?'已登记 SVP · 读取磁盘保存版本':'先导入 SVP，或登记已有工程';
 $('#productionSongState').textContent=have('song')?'已找到对应 Song':'可使用已保存 SVP 创建混音工程';
 $('#productionSeparationState').textContent=have('lead')&&have('accompaniment')?'主声与伴奏路径已登记':'分离后登记主声、伴奏与可选和声';
 $('#productionVideoState').textContent=link?.linked?link.linked.name+' · '+link.linked.cueCount+' 组视频字幕':'首次创建可带入混音与已保存字幕';
 $('#productionNext').textContent=!current()?'先导入已保存的 SVP，或直接使用素材分离与混音模板。':link?.linked?'已关联「'+link.linked.name+'」。可以继续视频，也可随时回 SV 或 Studio One 修改。':have('song')?'已有混音工程。完成混音后，在「管理文件路径」登记成品音频，再进入本曲视频。':have('svp')?'SVP 已登记。你可以继续在 SV 制作，或用它搭建 Studio One 混音工程。':'请先登记 SV 工程。';
 document.querySelectorAll('[data-asset-open]').forEach(b=>b.disabled=!have(b.dataset.assetOpen));
 $('#productionManage').disabled=!current();$('#separationManageAssets').disabled=!current();$('#productionBuildSong').disabled=!have('svp');
 renderAssetFiles('#productionAssetList',['svp','song','mix','lead','accompaniment','harmony','source']);
 renderAssetFiles('#separationAssetList',['source','lead','harmony','accompaniment']);
}
async function refresh(){const id=current(),token=++request;assets=null;link=null;paint();if(!id)return;try{const results=await Promise.all([api('/api/project-assets/'+id),api('/api/music-video/'+id)]);if(token!==request||id!==current()||exited)return;[assets,link]=results;paint();}catch(e){if(token===request)$('#productionNext').textContent=e.message;}}
async function openAsset(key,action='open'){if(!current())return;try{await api('/api/project-asset-open/'+current(),{asset:key,action});toast(action==='folder'?'已在文件管理器中定位':'已请求在原生软件中打开工程');}catch(e){toast(e.message);}}
async function manageAssets(){const id=current();if(!id){toast('请先导入对应的音乐工程');return;}$('#productionAssetError').textContent='';try{const data=await api('/api/project-assets/'+id);if(id!==current())return;assetProject=id;assetSnapshot=data;for(const [key,item] of Object.entries(data.assets))$('#productionPath_'+key).value=item.path;assetDialog.showModal();}catch(e){toast(e.message);}}
$('#productionAssetClose').onclick=()=>assetDialog.close();$('#productionManage').onclick=manageAssets;$('#separationManageAssets').onclick=manageAssets;
assetDialog.querySelectorAll('[data-production-pick]').forEach(b=>b.onclick=()=>{const key=b.dataset.productionPick;picker('productionPath_'+key,key==='svp'?'svp':key==='song'?'song':'audio','选择'+labels[key]);});
$('#productionAssetForm').onsubmit=async e=>{e.preventDefault();e.submitter.disabled=true;$('#productionAssetClose').disabled=true;try{const fields={};for(const [key,item] of Object.entries(assetSnapshot.assets)){const value=$('#productionPath_'+key).value;if(value!==item.path)fields[key]=value;}await api('/api/project-assets/'+assetProject,{revision:assetSnapshot.revision,assets:fields});assetDialog.close();await refresh();window.dispatchEvent(new Event('cw-project-assets-change'));toast('素材路径已保存，原文件与视频配置保持原样');}catch(err){$('#productionAssetError').textContent=err.message;}finally{e.submitter.disabled=false;$('#productionAssetClose').disabled=false;}};
assetDialog.addEventListener('cancel',e=>{if($('#productionAssetClose').disabled)e.preventDefault();});
document.querySelectorAll('[data-asset-open]').forEach(b=>b.onclick=()=>openAsset(b.dataset.assetOpen));
$('#productionBuildSong').onclick=()=>{if(!assets)return;$('#dawSVP').value=assets.assets.svp.path;$('#dawAccompaniment').value=assets.assets.accompaniment.path;$('#dawName').value=bundle.project.title.match(/^[A-Za-z0-9][A-Za-z0-9 _.-]{0,63}$/)?bundle.project.title:pid;invalidateDaw();tab('daw');updateDawOutput();};
$('#productionRefresh').onclick=()=>refresh();
function legacy(enabled){window.CWLegacyEnabled=enabled;$('#legacyToolsEnabled').checked=enabled;document.querySelectorAll('[data-legacy-tab],[data-legacy-content],#legacyWorkflow').forEach(el=>el.hidden=!enabled);$('#reportButton').hidden=!enabled;if($('#useLyricTiming'))$('#useLyricTiming').hidden=!enabled;if(!enabled&&['review','compare','files'].includes($('.tabs .active')?.dataset.tab))tab('workflow');if(!enabled){audio.pause();audio.removeAttribute('src');audio.load();}if(enabled&&bundle){setAudio();renderStats();renderFlags();renderNote();renderComparison();renderFiles();draw();}}
$('#legacyToolsEnabled').onchange=()=>legacy($('#legacyToolsEnabled').checked);
async function checkService(){const token=++probeRequest;$('#msstCheck').disabled=true;try{const result=await api('/api/separation');if(token!==probeRequest||exited)return;service=result;$('#msstBadge').textContent=result.ready?'已连接':result.starting?'启动中':'未连接';$('#msstBadge').classList.toggle('ready',result.ready);$('#msstStatus').textContent=result.message;$('#msstAddress').textContent=result.url;$('#msstOpen').href=result.url;$('#msstLaunch').disabled=result.ready||result.starting||!result.canLaunch;$('#msstEmbed').disabled=!result.ready;clearTimeout(serviceTimer);if(result.starting&&!$('#separation').hidden&&!document.hidden)serviceTimer=setTimeout(checkService,3000);}catch(e){$('#msstStatus').textContent=e.message;}finally{if(token===probeRequest)$('#msstCheck').disabled=false;}}
$('#msstCheck').onclick=checkService;$('#msstLaunch').onclick=async()=>{const b=$('#msstLaunch');b.disabled=true;try{const result=await api('/api/separation-launch/local',{});$('#msstStatus').textContent=result.message;await checkService();}catch(e){$('#msstStatus').textContent=e.message;b.disabled=false;}};
$('#msstEmbed').onclick=()=>{if(!service?.ready)return;if(!$('#msstEmbeddedFrame')){const frame=document.createElement('iframe');frame.id='msstEmbeddedFrame';frame.title='MSST 本机素材分离';frame.src=service.url;frame.referrerPolicy='no-referrer';$('#msstFrameMount').append(frame);}$('#msstFrameShell').hidden=false;$('#msstFrameShell').scrollIntoView({behavior:'smooth',block:'start'});};
$('#msstCloseEmbed').onclick=()=>{$('#msstFrameMount').replaceChildren();$('#msstFrameShell').hidden=true;};
$('#msstSettings').onclick=async()=>{try{const data=await api('/api/settings');for(const key of ['msstUrl','msstLauncher'])$('#'+key).value=data.settings[key];$('#msstSettingsError').textContent='';serviceDialog.showModal();}catch(e){toast(e.message);}};
$('#msstSettingsClose').onclick=()=>serviceDialog.close();$('#msstPickLauncher').onclick=()=>picker('msstLauncher','launcher','选择已安装的 MSST 启动程序 / 快捷方式');
$('#msstSettingsForm').onsubmit=async e=>{e.preventDefault();e.submitter.disabled=true;try{await api('/api/settings/new',{msstUrl:$('#msstUrl').value,msstLauncher:$('#msstLauncher').value});serviceDialog.close();$('#msstFrameMount').replaceChildren();$('#msstFrameShell').hidden=true;await checkService();toast('MSST 本机设置已保存');}catch(err){$('#msstSettingsError').textContent=err.message;}finally{e.submitter.disabled=false;}};
window.addEventListener('cw-music-project-loading',()=>{request++;assets=null;link=null;paint();});window.addEventListener('cw-music-project-change',refresh);
window.addEventListener('cw-workspace-change',e=>{if(e.detail.tab==='separation')checkService();else clearTimeout(serviceTimer);if(e.detail.tab==='workflow')refresh();});
window.addEventListener('cw-video-project-state',()=>{if(!$('#workflow').hidden)refresh();});
document.addEventListener('visibilitychange',()=>{if(document.hidden)clearTimeout(serviceTimer);});
window.addEventListener('cw-workbench-exit',()=>{exited=true;request++;probeRequest++;clearTimeout(serviceTimer);});
legacy(false);paint();if(current())refresh();if(!$('#separation').hidden)checkService();
})();
