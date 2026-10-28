/* Persisted export-source choice; comparison listening remains explicitly separate. */
(() => {
'use strict';
const ui=window.CWVideoStudio,$=s=>document.querySelector(s);
let last='',source='';
const exportLabel=document.createElement('label');exportLabel.innerHTML='<span>导出音源</span><select id="exportAudioSource"><option value="mix">外部混音</option><option value="video">视频原声（无需另选音频）</option></select><small id="exportAudioHint" class="hint"></small>';$('#output > h2').after(exportLabel);
$('#exportAudioSource').onchange=e=>{$('#audioSource').value=e.target.value;$('#audioSource').dispatchEvent(new Event('input'));};
const notice=document.createElement('small');notice.id='outputAudioNotice';notice.className='hint';notice.setAttribute('role','status');$('.preview-monitor').append(notice);
function update(){
 const {doc,exact}=ui.get();if(!doc)return;const selected=doc.audioSource||'mix',changed=last===doc.id&&source!==selected;
 if(last!==doc.id||changed){ui.stop();$('#listen').value='output';last=doc.id;source=selected;}
 const original=selected==='video';$('#audioSource').value=selected;$('#exportAudioSource').value=selected;
 for(const id of ['audio','applyAudio','audioOffset','gainDb','audioMode','targetLufs']){
  const el=$('#'+id);if(el)el.disabled=original||(id==='gainDb'&&doc.audioMode!=='gain')||(id==='targetLufs'&&doc.audioMode!=='normalize');
 }
 $('[data-target="audio"]').disabled=original;$('#analyze').disabled=original||!!doc.composition;
 $('#audioSourceHint').textContent=original?'使用当前可见视频的内嵌音轨，保留原音量；图片、无音片段与空白补静音。忽略外部混音偏移及响度设置，字幕时间不移动。':'使用下面选择的独立混音，并应用其偏移、增益或响度设置。';
 $('#exportAudioHint').textContent=original?'跟随可见画面的原声，保留原音量；无音片段补静音。':'使用已选择的独立混音及其声音设置。';
 const actual=original?'视频原声':'外部混音';
 notice.textContent=exact?'准确预览音源：'+(exact.audioSource==='video'?'视频原声':'外部混音')+' · 任务快照的渲染声音':$('#listen').value==='output'?'试听与导出：'+actual: '仅对比监听 · 导出仍使用：'+actual+'；选择“跟随导出音源”恢复';
 $('.monitor-listen').title='默认跟随导出音源；其他选项仅用于对比，不改变成片音源';
 if(original&&ui.listenSource()==='original')ui.cover.pause();
 if(changed){ui.notify('output-source');window.CWVideoEdit?.sync(true);}
}
$('#listen').addEventListener('change',update);
window.addEventListener('cw-video-change',e=>{if(['open','document','edit','history','save','preview','raw'].includes(e.detail.type))update();});
ui.ready.then(update);
})();
