/* Durable music/video links; material replacement is explicit and revision guarded. */
(() => {
'use strict';
const $=s=>document.querySelector(s),host=window.CWVideoHost;
let cardRequest=0,barRequest=0,dialogRequest=0,dialogMusic=null,info=null,busy=false,closed=false,barVideo=null,musicLoading=false;
const dialog=document.createElement('dialog');dialog.id='musicVideoDialog';dialog.className='music-video-dialog';dialog.setAttribute('aria-labelledby','mvTitle');dialog.setAttribute('aria-describedby','mvDescription');
dialog.innerHTML=`<form id="mvForm"><div class="mv-heading"><div><span class="eyebrow">CONNECTED WORKFLOW</span><h2 id="mvTitle">关联视频制作</h2></div><button type="button" class="button ghost" id="mvClose">关闭</button></div><p id="mvDescription"></p><div id="mvSources" class="mv-sources"></div><p id="mvDraftNotice" class="mv-notice" hidden>音乐页的字幕有未保存修改。当前带入的是已保存版本。<button type="button" class="button ghost" id="mvSaveDraft">保存字幕草稿并刷新</button></p><label class="field">使用的成品混音<select id="mvAudioChoice"></select></label><div class="mv-custom"><input id="mvAudioPath" placeholder="可另选成品 WAV / FLAC，支持带引号的路径"><button type="button" class="button ghost" id="mvPickAudio">浏览</button><button type="button" class="button ghost" id="mvPreview">读取素材</button></div><label class="field">关联方式<select id="mvMode"></select></label><div id="mvCreateFields"><label class="field">新视频工程名 · 支持中文、日语和空格<input id="mvName" maxlength="255"></label><p class="mv-note">自动带入混音引用和当前可用字幕；MV 可在视频区选择或下载。字幕使用混音时间，首次选择 MV 后只补音频偏移的差值。</p></div><div id="mvBindFields" hidden><label class="field">已有视频工程<select id="mvExisting"></select></label><p class="mv-note">建立入口关联，保留已有视频的音轨、字幕、偏移和样式。</p></div><div id="mvUpdateFields" hidden><label class="mv-check"><input type="checkbox" id="mvUpdateAudio">带入所选成品混音，保留已有字幕时间与样式</label><label class="mv-check"><input type="checkbox" id="mvUpdateCaptions">替换字幕文字与时间，重置逐句样式及额外微调</label><p class="mv-note" id="mvCompatibility"></p><p class="mv-note">应用后重新载入视频；保留全局字幕样式，旧版配置保留在 History 中。更换混音后请重新试听对齐。</p></div><p id="mvError" class="mv-error" role="status"></p><div class="mv-actions"><button type="button" id="mvUnlink" class="button ghost" hidden>解除关联</button><button type="submit" class="button" id="mvSubmit">创建并进入视频</button></div></form>`;
document.body.append(dialog);
function activeMusic(){return !musicLoading&&bundle?.project?.id===pid?pid:null;}
function draftChanged(id){return activeMusic()===id&&JSON.stringify(subtitleDraft)!==JSON.stringify(bundle.state.subtitles);}
async function preview(id,audioPath=null){return audioPath!==null?api('/api/music-video/'+encodeURIComponent(id),{action:'preview',audioPath}):api('/api/music-video/'+encodeURIComponent(id));}
function openVideo(id){host.open(id);}
async function refreshCard(){
 const id=activeMusic(),token=++cardRequest;$('#musicVideoCard').hidden=!id;if(!id)return;
 $('#musicVideoOpen').disabled=true;$('#musicVideoSummary').textContent='正在读取对应视频与素材…';
 try{const data=await preview(id);if(token!==cardRequest||activeMusic()!==id)return;$('#musicVideoLabel').textContent=data.linked?'对应视频 · '+data.linked.name:'为「'+data.music.title+'」接上视频制作';$('#musicVideoOpen').textContent=data.linked?'进入本曲视频':'创建关联视频';$('#musicVideoSummary').textContent=[data.audio?'成品混音已找到':'尚未登记成品混音',data.linked?`视频已有 ${data.linked.cueCount} 组字幕（保留当前编辑）`:`${data.captions.count} 组字幕 · ${data.captions.translation} 组含译文`,data.changed.audio||data.changed.captions?'音乐侧有新素材可更新':''].filter(Boolean).join(' · ');}
 catch(e){if(token===cardRequest)$('#musicVideoSummary').textContent=e.message;}
 finally{if(token===cardRequest){$('#musicVideoOpen').disabled=false;$('#musicVideoManage').disabled=busy;}}
}
async function enterMusicVideo(){
 const id=activeMusic();if(!id){toast('歌曲正在载入，请稍后再试');return;}
 try{const data=await preview(id);if(activeMusic()!==id)return;if(data.linked)openVideo(data.linked.id);else await showDialog(id);}
 catch(e){toast(e.message);}
}
function setBusy(value){busy=value;$('#mvSubmit').disabled=value||!info;for(const id of ['mvClose','mvUnlink','musicVideoManage','mvManageFromVideo','mvLinkCurrent']){const button=$('#'+id);if(button)button.disabled=value;}}
function updateMode(){
 const selected=$('#mvMode').value;
 $('#mvCreateFields').hidden=selected!=='create';$('#mvBindFields').hidden=selected!=='bind';$('#mvUpdateFields').hidden=selected!=='update';
 $('#mvSubmit').textContent=selected==='create'?'创建并进入视频':selected==='bind'?'确认关联并进入':'应用所选素材';
 const compatible=info?.captionCompatible||$('#mvUpdateAudio').checked;
 $('#mvUpdateCaptions').disabled=!info?.captions.count||!compatible;
 if($('#mvUpdateCaptions').disabled)$('#mvUpdateCaptions').checked=false;
 $('#mvUpdateAudio').disabled=!info?.audio;
 $('#mvCompatibility').textContent=compatible?'字幕按当前音频偏移带入一次，原文与译文一起更新。':'当前视频音轨和音乐侧混音不同。要更新字幕，请同时带入混音，以免套用不同的时间基准。';
}
function renderInfo(data,initial=false){
 info=data;$('#mvTitle').textContent='「'+data.music.title+'」的视频制作';$('#mvDescription').textContent=data.linked?'对应视频：'+data.linked.name+'。直接进入会保留视频侧已有修改。':'先建立一次关联，以后从这首歌即可直接进入。';
 const audio=data.audio,sub=data.captions;
 $('#mvSources').innerHTML=`<div><strong>成品混音</strong><span>${escapeHTML(audio?audio.name:'暂未找到')}</span><small>${escapeHTML(audio?audio.path:'可在下方选择自己的成品混音；不会使用分离主声或伴奏代替。')}</small></div><div><strong>双语字幕</strong><span>${sub.count} 组 · ${sub.original} 组原文 / ${sub.translation} 组译文</span><small>${escapeHTML(sub.issue||sub.label)}${sub.count?' · 时间仍需试听确认':''}</small></div>`;
 $('#mvDraftNotice').hidden=!draftChanged(dialogMusic);
 if(initial){$('#mvName').value=data.defaultName;$('#mvAudioPath').value=data.audioSelection;$('#mvAudioChoice').replaceChildren(new Option('自动选取 · 最新已完成交付或已登记混音',''),...data.audioCandidates.map(c=>new Option(c.label+' · '+c.name,c.path)));$('#mvAudioChoice').value=data.audioSelection;$('#mvMode').replaceChildren(...(data.linked?[new Option('更新对应视频的素材','update')]:[new Option('新建关联视频工程','create')]),new Option('关联已有视频工程','bind'));$('#mvExisting').replaceChildren(...data.videos.map(v=>{const o=new Option(v.name+(v.musicId&&v.musicId!==dialogMusic?' · 已关联 '+v.musicTitle:''),v.id);o.disabled=!!v.musicId&&v.musicId!==dialogMusic;return o;}));$('#mvUpdateAudio').checked=false;$('#mvUpdateCaptions').checked=false;}
 $('#mvUnlink').hidden=!data.linkedId;updateMode();
}
async function refreshDialog(initial=false){
 const token=++dialogRequest,id=dialogMusic;setBusy(true);$('#mvError').textContent='';
 try{const data=await preview(id,initial?null:$('#mvAudioPath').value.trim());if(token!==dialogRequest||id!==dialogMusic)return;renderInfo(data,initial);}
 catch(e){if(token===dialogRequest){info=null;$('#mvError').textContent=e.message;}}
 finally{if(token===dialogRequest)setBusy(false);}
}
async function showDialog(id,{bindVideo=null}={}){
 if(busy||dialog.open||closed)return;dialogMusic=id;info=null;setBusy(true);$('#mvSources').textContent='正在读取素材…';$('#mvError').textContent='';dialog.showModal();
 try{const data=await preview(id);if(data.linked)await host.prepare(data.linked.id);await refreshDialog(true);if(bindVideo&&info){$('#mvMode').value='bind';$('#mvExisting').value=bindVideo;updateMode();}}
 catch(e){$('#mvError').textContent=e.message;setBusy(false);}
}
function close(){if(busy)return;dialogRequest++;dialog.close();}
$('#mvClose').onclick=close;dialog.addEventListener('cancel',e=>{if(busy)e.preventDefault();else dialogRequest++;});
$('#mvMode').onchange=updateMode;$('#mvUpdateAudio').onchange=updateMode;
$('#mvAudioChoice').onchange=()=>{$('#mvAudioPath').value=$('#mvAudioChoice').value;refreshDialog();};
$('#mvPreview').onclick=()=>refreshDialog();$('#mvAudioPath').oninput=()=>{$('#mvError').textContent='混音路径已修改，点击「读取素材」确认后再应用。';$('#mvSubmit').disabled=true;};
// Reuse the workbench's sorted local file picker without uploading any media.
$('#mvPickAudio').onclick=()=>{dawPicker={kind:'audio',target:'mvAudioPath'};$('#dawPickerTitle').textContent='选择成品混音';$('#dawPickerChoose').hidden=true;$('#dawPickerHint').textContent='选择最终混音 WAV / FLAC 等文件。';$('#dawFilePicker').showModal();browseDawPath($('#mvAudioPath').value||info?.audio?.path||'');};
$('#mvSaveDraft').onclick=async()=>{const id=dialogMusic;if(activeMusic()!==id)return;setBusy(true);try{const r=await api('/api/state/'+id,{subtitles:subtitleDraft});if(activeMusic()===id){bundle.state=r.state;renderSubtitles();}await refreshDialog();}catch(e){$('#mvError').textContent=e.message;}finally{setBusy(false);}};
$('#mvForm').onsubmit=async e=>{
 e.preventDefault();if(busy||!info)return;setBusy(true);const id=dialogMusic,data=info,action=$('#mvMode').value;
 try{const body={action,sourceSignature:data.signature,audioPath:$('#mvAudioPath').value.trim()};if(action==='create')body.name=$('#mvName').value;else if(action==='bind'){body.videoId=$('#mvExisting').value;body.expectedVideoId=data.linkedId;}else{body.videoId=data.linked.id;body.revision=data.linked.revision;body.audio=$('#mvUpdateAudio').checked;body.captions=$('#mvUpdateCaptions').checked;}
  const result=await api('/api/music-video/'+encodeURIComponent(id),body);dialog.close();if(action==='update')await host.reload(result.videoId);else openVideo(result.videoId);await refreshCard();barVideo=null;refreshBar();toast(action==='update'?'所选素材已更新，请试听检查时间与音量':'歌曲与视频已关联');
 }catch(e){$('#mvError').textContent=e.message;}
 finally{setBusy(false);}
};
$('#mvUnlink').onclick=async()=>{if(!info||busy)return;setBusy(true);try{await api('/api/music-video/'+dialogMusic,{action:'unlink',expectedVideoId:info.linkedId});dialog.close();await refreshCard();barVideo=null;refreshBar();toast('已解除入口关联，音乐与视频工程均保留');}catch(e){$('#mvError').textContent=e.message;}finally{setBusy(false);}};
async function refreshBar(){
 const id=host.state()?.id,bar=$('#videoMusicBar');if(!id){bar.hidden=true;return;}if(id===barVideo)return;barVideo=id;const token=++barRequest;
 try{const data=await api('/api/video-music/'+encodeURIComponent(id));if(token!==barRequest||host.state()?.id!==id)return;bar.hidden=false;
  if(data.music){bar.innerHTML=`<div><strong>♫ ${escapeHTML(data.music.title)}</strong><small>已关联音乐工程</small></div><div><button class="button ghost" id="mvReturnMusic">回到这首歌</button><button class="button ghost" id="mvManageFromVideo">更新素材 / 关联设置</button></div>`;$('#mvReturnMusic').onclick=async()=>{try{if(activeMusic()!==data.music.id)await loadProject(data.music.id);$('.tabs [data-tab="workflow"]').click();}catch(e){toast(e.message);}};$('#mvManageFromVideo').onclick=()=>showDialog(data.music.id);}
  else{bar.innerHTML=`<div><strong>关联音乐工程</strong><small>建立歌曲到当前视频的入口</small></div><div><select id="mvMusicChoice" aria-label="关联的音乐工程"></select><button class="button ghost" id="mvLinkCurrent">建立关联</button></div>`;$('#mvMusicChoice').replaceChildren(new Option('选择对应歌曲',''),...data.choices.map(p=>new Option(p.title+(p.artist?' · '+p.artist:''),p.id)));$('#mvLinkCurrent').onclick=()=>{const selected=$('#mvMusicChoice').value;if(!selected){toast('请选择这支视频对应的歌曲');return;}showDialog(selected,{bindVideo:id});};}
 }catch(e){barVideo=null;bar.hidden=false;bar.textContent=e.message;}
}
$('#musicVideoManage').onclick=()=>activeMusic()&&showDialog(activeMusic());$('#videoLibrary').onclick=()=>host.open();
document.addEventListener('click',e=>{if(e.target.closest('[data-music-video-open]'))enterMusicVideo();});
document.addEventListener('click',e=>{if(!e.isTrusted||document.body.classList.contains('is-video-workspace')||!projects.length)return;if(e.target.closest('.tabs [data-tab="video"],[data-workspace="video"]')){e.preventDefault();e.stopImmediatePropagation();enterMusicVideo();}},true);
document.addEventListener('click',e=>{if(e.target.closest('#projects [data-project]'))$('.tabs [data-tab="workflow"]').click();},true);
window.addEventListener('cw-project-assets-change',refreshCard);
window.addEventListener('cw-music-project-loading',()=>{musicLoading=true;cardRequest++;$('#musicVideoOpen').disabled=true;$('#musicVideoManage').disabled=true;$('#musicVideoSummary').textContent='正在切换歌曲…';});
window.addEventListener('cw-music-project-change',()=>{musicLoading=false;refreshCard();});window.addEventListener('cw-video-project-state',refreshBar);
window.addEventListener('focus',()=>{if(!closed&&activeMusic())refreshCard();});window.addEventListener('cw-workbench-exit',()=>{closed=true;cardRequest++;barRequest++;dialogRequest++;});
if(activeMusic())refreshCard();if(host.state()?.id)refreshBar();
})();
