/* Legacy links now open the shared workbench shell; standalone remains explicit. */
(() => {
const query=new URLSearchParams(location.search);let embedded=false;
try{embedded=window.parent!==window&&window.parent.location.origin===location.origin&&query.get('embed')==='1';}catch{}
window.CW_VIDEO_EMBEDDED=embedded;
if(embedded)document.documentElement.classList.add('embedded');
else if(query.get('standalone')!=='1'){const target=new URL('/',location.origin);target.searchParams.set('tab','video');if(query.get('project'))target.searchParams.set('videoProject',query.get('project'));location.replace(target);}
})();
