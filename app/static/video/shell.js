/* Same-origin host integration; subtitle data stays inside the editor. */
(() => {
'use strict';if(!window.CW_VIDEO_EMBEDDED)return;
const ui=window.CWVideoStudio,host=window.parent.CWVideoHost;if(!host)return;
let alive=true;
function state(){const {doc,dirty}=ui.get();return {id:doc?.id||null,name:doc?.name||'',dirty,projects:[...document.querySelector('#projects').options].filter(o=>o.value).map(o=>({id:o.value,name:o.textContent.replace(/ · r\d+$/,''),revision:Number(o.textContent.match(/ · r(\d+)$/)?.[1]||0)}))};}
function publish(){if(alive)host.update(state());}
window.addEventListener('cw-video-change',publish);
window.addEventListener('cw-workbench-exit',()=>{alive=false;},{once:true});
ui.ready.then(()=>{if(!alive)return;host.ready({state,visible:ui.setVisible,navigate:async id=>{if(ui.get().doc?.id===id)return;if(ui.get().dirty)await ui.save();await ui.open(id);},refresh:ui.refresh,create:()=>document.querySelector('#new').click(),save:ui.save,undo:ui.history.undo,redo:ui.history.redo});});
})();
