'use strict';
let desktopIconState=null,desktopIconChoice=null,desktopIconBusy=false,desktopIconRequest=0;
function renderDesktopIcons(){
 const state=desktopIconState;
 $('#desktopIconChoices').innerHTML=state.variants.map((v,i)=>`<article class="desktop-icon-card ${v.id===desktopIconChoice?'selected':''}"><button class="desktop-icon-option" role="radio" aria-checked="${v.id===desktopIconChoice}" data-desktop-icon="${v.id}" aria-label="${escapeHTML(v.name)}"><span class="desktop-icon-number">0${i+1}<span>${state.shortcutExists&&state.selected===v.id?'桌面正在使用':'&nbsp;'}</span></span><img src="${v.preview}" alt="" width="180" height="180"><strong>${escapeHTML(v.name)}</strong><span class="desktop-icon-english">${escapeHTML(v.english)}</span><span class="desktop-icon-desc">${escapeHTML(v.description)}</span><span class="desktop-icon-radio" aria-hidden="true"></span></button><a href="${v.download}" download>下载 ICO ↗</a></article>`).join('');
 $$('[data-desktop-icon]').forEach((b,i)=>{
  b.disabled=desktopIconBusy;
  b.onclick=()=>{if(desktopIconBusy)return;desktopIconChoice=b.dataset.desktopIcon;renderDesktopIcons();$(`[data-desktop-icon="${desktopIconChoice}"]`).focus()};
  b.onkeydown=e=>{if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)||desktopIconBusy)return;e.preventDefault();const next=(i+(['ArrowRight','ArrowDown'].includes(e.key)?1:-1)+state.variants.length)%state.variants.length;desktopIconChoice=state.variants[next].id;renderDesktopIcons();$(`[data-desktop-icon="${desktopIconChoice}"]`).focus()};
 });
 const current=state.variants.find(v=>v.id===state.selected);
 $('#desktopIconCurrent').textContent=state.shortcutExists?'当前桌面图标：'+(current?.name||'自定义图标'):'桌面快捷方式尚未创建';
 $('#desktopIconShortcut').textContent=state.shortcut;
 $('#desktopIconApply').disabled=desktopIconBusy||!state.canApply||!desktopIconChoice||(state.shortcutExists&&desktopIconChoice===state.selected);
 $('#desktopIconApply').textContent=desktopIconBusy?'正在应用…':state.shortcutExists?'应用到桌面':'创建桌面快捷方式';
 if(!state.canApply)$('#desktopIconStatus').textContent='桌面同名快捷方式指向其他程序，无法在这里替换。';
 else if(!desktopIconBusy)$('#desktopIconStatus').textContent=state.shortcutExists&&desktopIconChoice!==state.selected?'已选择 '+state.variants.find(v=>v.id===desktopIconChoice)?.name+'；点击应用后更新桌面。':'图标在本机保存，启动配置保持不变。';
}
$('#desktopIconSettings').onclick=async()=>{
 const request=++desktopIconRequest;
 $('#desktopIconDialog').showModal();$('#desktopIconChoices').innerHTML='<p class="desktop-icon-loading">正在读取桌面快捷方式…</p>';$('#desktopIconApply').disabled=true;
 try{
  const state=await api('/api/desktop');if(request!==desktopIconRequest)return;
  desktopIconState=state;desktopIconChoice=state.selected||state.variants[0].id;renderDesktopIcons();
 }catch(e){$('#desktopIconStatus').textContent=e.message;$('#desktopIconCurrent').textContent='读取未完成'}
};
function closeDesktopIconDialog(){if(desktopIconBusy)return;desktopIconRequest++;$('#desktopIconDialog').close()}
$('#desktopIconClose').onclick=closeDesktopIconDialog;
$('#desktopIconDialog').addEventListener('cancel',e=>{if(desktopIconBusy)e.preventDefault();else desktopIconRequest++});
$('#desktopIconApply').onclick=async()=>{
 if(desktopIconBusy||!desktopIconChoice||!desktopIconState?.canApply)return;
 desktopIconBusy=true;$('#desktopIconClose').disabled=true;renderDesktopIcons();
 try{
  const result=await api('/api/desktop-icon/new',{icon:desktopIconChoice});
  desktopIconState={...desktopIconState,...result};desktopIconChoice=result.selected;
  $('#desktopIconStatus').textContent='桌面图标已更新。';toast('桌面快捷方式图标已更新');
 }catch(e){$('#desktopIconStatus').textContent=e.message;toast(e.message)}
 finally{desktopIconBusy=false;$('#desktopIconClose').disabled=false;const message=$('#desktopIconStatus').textContent;renderDesktopIcons();$('#desktopIconStatus').textContent=message}
};
