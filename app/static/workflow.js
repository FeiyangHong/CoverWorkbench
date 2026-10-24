/* Workflow desk: native editing, local media delivery. */
'use strict';
let workflowState=null, workflowRequest=0, phraseFingerprint='';
const workStatus={queued:'等待执行',running:'处理中',completed:'已完成',failed:'失败',interrupted:'已中断'};
async function refreshWorkflow(reset=false){
 const id=pid,request=++workflowRequest;const state=await api('/api/workflow/'+id);
 if(id!==pid||request!==workflowRequest)return;workflowState=state;
 $('#renderFolder').textContent=state.renderFolder;
 $('#watchEnabled').checked=!!state.watcher.enabled;
 $('#watchDescription').textContent=state.watcher.message||'启用后，新渲染文件稳定 10 秒即自动检查并打包。';
 $('#nativeInventory').textContent='调声预设：'+((state.presets||[]).map(p=>p.id+' (SV'+p.svMajor+')').join('、')||'尚未保存')+'；本曲乐句：'+((state.phrases||[]).join('、')||'尚未保存');
 if(reset){$('#deliveryAudio').value=state.defaultAudio;renderPhrasePrep()}
 if(phraseFingerprint!==JSON.stringify(bundle?.lyricPackage?.rows||[]))renderPhrasePrep();
 $('#jobCount').textContent=state.jobs.filter(j=>['running','queued'].includes(j.status)).length+' 个任务进行中';
 $('#jobList').innerHTML=state.jobs.length?state.jobs.map(j=>`<article class="job-card ${j.status}"><div class="job-top"><strong>${j.kind==='delivery'?'音频检查与交付包':'视频换音轨'}${j.fromWatcher?' · 自动':''}</strong><span>${workStatus[j.status]||j.status}</span></div><small>${new Date(j.createdAt*1000).toLocaleString()} · ${escapeHTML(j.id)}</small><div class="job-progress"><i style="width:${j.progress}%"></i></div><p>${escapeHTML(j.message)}</p>${j.qc?`<div class="job-metrics"><span>${Number(j.qc.duration).toFixed(1)} s</span><span>${j.qc.lufs??'—'} LUFS</span><span>${j.qc.truePeakDBTP??'—'} dBTP</span></div>`:''}${(j.warnings||[]).map(w=>`<p class="job-warning">${escapeHTML(w)}</p>`).join('')}<div class="job-downloads">${j.files.map(f=>`<a href="${escapeHTML(f.url)}" download>${escapeHTML(f.label)} ↗</a>`).join('')}</div></article>`).join(''):'<div class="workflow-empty"><span>↗</span><strong>让重复步骤自己运行</strong><p>提交一份渲染音频，检查报告、歌词、字幕和交付包会一起整理好。</p></div>';
}
function nativePath(){if(!bundle)return;$('#nativeSV1').textContent=bundle.project.working;$('#nativeSV2').textContent=bundle.project.sv2Working}
function renderPhrasePrep(){
 const rows=bundle?.lyricPackage?.rows||[];
 phraseFingerprint=JSON.stringify(rows);
 $('#phraseLine').innerHTML=rows.map((r,i)=>`<option value="${i}">${i+1}. ${escapeHTML(r.original)}</option>`).join('')||'<option value="">先准备歌词素材</option>';
 preparePhrase();
}
function preparePhrase(){
 const rows=bundle?.lyricPackage?.rows||[],row=rows[Number($('#phraseLine').value)];
 $('#phraseOriginal').textContent=row?.original||'到「歌词与字幕」选择歌曲版本，导入本机缓存或在线搜索。';
 $('#phraseReading').textContent=row?.reading?`读音：${row.reading} · ${row.readingSource||'来源待确认'}`:'读音未提供，请填写并确认。';
 $('#phraseRomaji').textContent=row?.romaji?'罗马音：'+row.romaji:'';
 let text='';
 if(row){
  const raw=bundle.project.language==='ja'?(row.reading||''):row.original;
  const tokens=[];for(const c of raw.replace(/[\s、。！？!?，,.「」『』（）()：:；;…・]/g,'')){
   if('ゃゅょぁぃぅぇぉャュョァィゥェォ'.includes(c)&&tokens.length)tokens[tokens.length-1]+=c;else tokens.push(c);
  }
  text=tokens.join(' ');
 }
 $('#phraseTokens').value=text;tokenCount();
}
function tokenCount(){const count=$('#phraseTokens').value.trim().split(/\s+/).filter(Boolean).length;$('#tokenCount').textContent=count+' 项 · 必须与 SV 所选音符数量一致'}
async function submitWork(kind,button){
 const id=pid;button.disabled=true;
 try{
  const body={kind,audio:$('#deliveryAudio').value};
  await api('/api/jobs/'+id,body);if(id===pid)await refreshWorkflow();toast('任务已加入队列，可以继续在 SV 工作');
 }catch(e){toast(e.message)}finally{button.disabled=false}
}
const originalLoadWorkflow=loadProject;
loadProject=async function(id){await originalLoadWorkflow(id);if(pid===id&&bundle){nativePath();await refreshWorkflow(true)}};
$$('.tabs [data-tab]').forEach(b=>{const previous=b.onclick;b.onclick=e=>{previous?.(e);$('.live-strip').hidden=b.dataset.tab!=='review';if(b.dataset.tab==='workflow')refreshWorkflow().catch(e=>toast(e.message))}});
$('.live-strip').hidden=true;
$$('[data-open-tab]').forEach(b=>b.onclick=()=>$('.tabs [data-tab="'+b.dataset.openTab+'"]').click());
$('#phraseLine').onchange=preparePhrase;$('#phraseTokens').oninput=tokenCount;
$('#copyPhrase').onclick=async()=>{try{await navigator.clipboard.writeText($('#phraseTokens').value);toast('歌词单位已复制；在 SV 选音符并运行 CW Phrase Lyrics')}catch(e){$('#phraseTokens').select();toast('请按 Ctrl+C 复制所选内容')}};
$('#submitDelivery').onclick=()=>submitWork('delivery',$('#submitDelivery'));
$('#refreshJobs').onclick=()=>refreshWorkflow().catch(e=>toast(e.message));
$('#watchEnabled').onchange=async()=>{try{await api('/api/watcher/'+pid,{enabled:$('#watchEnabled').checked});await refreshWorkflow()}catch(e){toast(e.message);refreshWorkflow()}};
const workflowPolling=setInterval(()=>{if(bundle&&!$('#workflow').hidden)refreshWorkflow().catch(()=>{})},2500);
window.addEventListener('cw-workbench-exit',()=>clearInterval(workflowPolling),{once:true});
