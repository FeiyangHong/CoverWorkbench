/* Explicit local-server exit, shared by the main workbench and standalone pages. */
(() => {
'use strict';
let instance=null, polling=null, revision=0, exiting=false, observed=false;
const channel=typeof BroadcastChannel==='function'?new BroadcastChannel('cw-service-lifecycle'):null;
let host=document.querySelector('.header-actions');
if(!host){host=document.createElement('nav');host.className='cw-service-bar';host.innerHTML='<a href="/">CoverWorkbench <span>本机工作台</span></a><a href="/video/index.html">视频制作</a>';document.body.prepend(host);}
const button=document.createElement('button');button.id='cwExitButton';button.className='cw-exit-button';button.type='button';button.textContent='⏻ 彻底退出';button.title='停止本机后台服务，释放工作台资源';host.append(button);
const dialog=document.createElement('dialog');dialog.id='cwExitDialog';dialog.className='cw-exit-dialog';dialog.setAttribute('aria-labelledby','cwExitTitle');
dialog.innerHTML=`<span class="cw-exit-eyebrow">CLOSE YOUR WORKBENCH</span><h2 id="cwExitTitle">退出本机工作台？</h2><p>确认后会停止 CoverWorkbench 后台服务和网页试听，所有工作台窗口都会断开连接。</p><p>请先保存网页里尚未提交的修改。SV 和 Studio One 会继续运行，工程文件保留。</p><div id="cwExitActivity" class="cw-exit-activity" role="status">正在检查后台任务…</div><p class="cw-exit-note">下次使用时，双击桌面快捷方式或运行工作台目录里的 Start.vbs。</p><div class="cw-exit-actions"><button id="cwExitCancel" type="button">取消</button><button id="cwExitConfirm" type="button" disabled>确认彻底退出</button></div>`;
document.body.append(dialog);
const $=selector=>dialog.querySelector(selector);
async function status(){const response=await fetch('/api/lifecycle',{cache:'no-store',signal:AbortSignal.timeout(3000)});const data=await response.json();if(!response.ok)throw Error(data.error||'无法读取后台状态');observed=true;return data;}
function activity(data){instance=data.instance;const tasks=[];if(data.auditions)tasks.push(`${data.auditions} 个试听任务`);if(data.videos)tasks.push(`${data.videos} 个视频制作任务`);if(data.deliveries)tasks.push(`${data.deliveries} 个交付／视频任务`);if(!tasks.length&&Object.keys(data.operations||{}).length)tasks.push('正在处理的网页请求或任务收尾');$('#cwExitActivity').textContent=data.canExit?'后台空闲，可以安全退出。':data.state==='stopping'?'后台正在退出…':tasks.join('、')+'，请等待完成后再退出。';$('#cwExitConfirm').disabled=!data.canExit;}
async function refresh(){const current=++revision;try{const data=await status();if(current===revision&&dialog.open&&!exiting)activity(data);}catch(error){if(current===revision&&dialog.open){$('#cwExitActivity').textContent='暂时无法连接后台，请确认工作台是否仍在运行。';$('#cwExitConfirm').disabled=true;}}}
button.onclick=()=>{if(exiting)return;dialog.showModal();$('#cwExitConfirm').disabled=true;refresh();polling=setInterval(refresh,2000);};
function stopPoll(){revision++;clearInterval(polling);polling=null;}
$('#cwExitCancel').onclick=()=>dialog.close();dialog.addEventListener('close',stopPoll);
async function showExit(targetInstance,confirmed=true){
 if(exiting)return;exiting=true;stopPoll();clearInterval(heartbeatTimer);channel?.close();
 window.dispatchEvent(new Event('cw-workbench-exit'));
 document.querySelectorAll('audio,video').forEach(media=>media.pause());
 document.querySelectorAll('dialog[open]').forEach(d=>d.close());
 const screen=document.createElement('section');screen.id='cwExitScreen';screen.className='cw-exit-screen';screen.setAttribute('aria-labelledby','cwExitScreenTitle');
 screen.innerHTML='<div class="cw-exit-card"><div class="cw-exit-symbol">⏻</div><span class="cw-exit-eyebrow">COVERWORKBENCH</span><h1 id="cwExitScreenTitle">正在退出工作台…</h1><p id="cwExitScreenStatus" role="status">正在等待本机后台停止。</p><p>再次使用时，请双击桌面快捷方式，或运行工作台目录里的 Start.vbs。</p><button id="cwReconnect" type="button" hidden>已重新启动？重新连接</button><small>SV、Studio One 和你的工程文件不受影响。</small></div>';
 [...document.body.children].forEach(node=>{node.inert=true;});document.body.append(screen);screen.tabIndex=-1;screen.focus();
 const title=screen.querySelector('#cwExitScreenTitle'),note=screen.querySelector('#cwExitScreenStatus'),reconnect=screen.querySelector('#cwReconnect');
 let misses=0;
 for(let attempt=0;confirmed&&attempt<15;attempt++){
  try{const data=await status();misses=0;if(data.instance!==targetInstance&&data.state==='running'){title.textContent='工作台已重新启动';note.textContent='旧后台已退出，检测到新的工作台服务。';reconnect.hidden=false;break;}}
  catch{if(++misses>=2){title.textContent='工作台已彻底退出';note.textContent='本机服务已断开连接，网页试听已停止。现在可以关闭此页面。';reconnect.hidden=false;break;}}
  await new Promise(resolve=>setTimeout(resolve,350));
 }
 if(!confirmed){title.textContent='后台连接已断开';note.textContent='网页试听已停止。可检查本机后台，或使用桌面快捷方式重新启动。';reconnect.hidden=false;}
 else if(reconnect.hidden){title.textContent='退出已请求，仍在等待后台';note.textContent='请稍后检查；若后台仍未退出，可使用工作台目录里的 Stop.ps1。';reconnect.hidden=false;}
 reconnect.onclick=async()=>{reconnect.disabled=true;try{const data=await status();if(data.state==='running')location.reload();else note.textContent='后台仍在退出，请稍候。';}catch{note.textContent='尚未重新启动，请先双击桌面快捷方式或运行 Start.vbs。';}finally{reconnect.disabled=false;}};
}
$('#cwExitConfirm').onclick=async()=>{
 stopPoll();$('#cwExitConfirm').disabled=true;$('#cwExitCancel').disabled=true;$('#cwExitActivity').textContent='正在请求停止后台…';
 try{
  const response=await fetch('/api/shutdown/local',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirm:true,instance}),signal:AbortSignal.timeout(6000)});
  const data=await response.json();
  if(!response.ok){if(response.status===409)activity(data);throw Error(data.error||'退出请求失败');}
  channel?.postMessage({type:'exit',instance:data.instance});await showExit(data.instance);
 }catch(error){$('#cwExitActivity').textContent=error.message;$('#cwExitCancel').disabled=false;if(!exiting){polling=setInterval(refresh,2000);refresh();}}
};
if(channel)channel.onmessage=event=>{const data=event.data;if(data?.type==='exit'&&typeof data.instance==='string')showExit(data.instance);};
async function checkConnection(){if(exiting||dialog.open||document.hidden)return;try{const data=await status();instance=data.instance;if(data.state==='stopping')showExit(data.instance);}catch{if(observed)showExit(instance,false);}}
// Different browser profiles cannot receive BroadcastChannel messages. A small,
// visible-page-only heartbeat also stops their cached audio after service exit.
const heartbeatTimer=setInterval(checkConnection,10000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)checkConnection();});checkConnection();
})();
