/* Frame-based picture operations. They never receive music or caption state. */
((root)=>{
'use strict';
const copy=value=>structuredClone(value);
const frame=(t,fps)=>Math.round(t*fps);
function checked(comp){
 const fps=comp.fps,rows=comp.clips.sort((a,b)=>a.start-b.start);
 if(rows.length>200)throw Error('画面最多 200 段，请减少片段后重试');
 if(comp.duration>21600)throw Error('成片不能超过 6 小时');
 for(let i=0;i<rows.length;i++){
  const c=rows[i],a=comp.assets.find(x=>x.id===c.asset);
  if(!a||a.kind==='audio'||c.start<0||frame(c.duration,fps)<1||c.start+c.duration>comp.duration+.001)throw Error('片段超出成片范围');
  if(a.kind==='video'&&(c.in<0||c.in+c.duration>a.duration+.001))throw Error('修剪超出源素材长度');
  if(i&&frame(c.start,fps)<frame(rows[i-1].start+rows[i-1].duration,fps))throw Error('这里已有画面；请选择「插入排序」，或移到空白区间');
 }
 return comp;
}
function insert(original,clip,at,{ripple=true,splitId}={}){
 const comp=copy(original),fps=comp.fps,t=frame(at,fps),length=frame(clip.duration,fps),total=frame(comp.duration,fps);
 if(!Number.isFinite(at)||t<0||t>total||length<1)throw Error('请选择有效的画面落点');
 const rows=[];
 for(const c of comp.clips){
  const a=frame(c.start,fps),b=frame(c.start+c.duration,fps);
  if(ripple&&a<t&&b>t){
   if(!splitId)throw Error('缺少分割片段编号');
   const image=comp.assets.find(x=>x.id===c.asset)?.kind==='image';
   const right={...copy(c),id:splitId,start:(t+length)/fps,in:image?0:c.in+(t-a)/fps,duration:(b-t)/fps};
   delete right.transition;c.duration=(t-a)/fps;rows.push(c,right);
  }else{if(ripple&&a>=t)c.start=(a+length)/fps;rows.push(c);}
 }
 rows.push({...copy(clip),start:t/fps,duration:length/fps});comp.clips=rows;
 comp.duration=Math.max(total+(ripple?length:0),t+length)/fps;
 return checked(comp);
}
function reorder(original,id,at){
 const comp=copy(original),fps=comp.fps,c=comp.clips.find(x=>x.id===id);
 if(!c)throw Error('片段已不存在，请重新选择');
 const start=frame(c.start,fps),length=frame(c.duration,fps),end=start+length,target=frame(at,fps);
 if(target>=start&&target<=end)return comp;
 comp.clips=comp.clips.filter(x=>x.id!==id);
 for(const row of comp.clips)if(frame(row.start,fps)>=end)row.start=(frame(row.start,fps)-length)/fps;
 comp.duration=(frame(comp.duration,fps)-length)/fps;
 delete c.transition;
 return insert(comp,c,(target>=end?target-length:target)/fps,{splitId:id+'Split'});
}
function slot(comp,at,exclude){
 const t=Math.max(0,Math.min(comp.duration,at)),row=comp.clips.find(c=>c.id!==exclude&&t>=c.start&&t<c.start+c.duration);
 return row?(t<row.start+row.duration/2?row.start:row.start+row.duration):frame(t,comp.fps)/comp.fps;
}
const api={insert,reorder,slot,checked};
if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.CWPictureEdits=api;
})(typeof window!=='undefined'?window:globalThis);
