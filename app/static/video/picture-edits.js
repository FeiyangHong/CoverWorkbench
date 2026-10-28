/* Frame-based picture operations. They never receive music or caption state. */
((root)=>{
'use strict';
const copy=value=>structuredClone(value);
const frame=(t,fps)=>Math.round(t*fps);
const trackOf=c=>c.track||'V1';
const tracks=comp=>comp.tracks||[{id:'V1',name:'视频 1',hidden:false}];
const clipsOn=(comp,id)=>comp.clips.filter(c=>trackOf(c)===id).sort((a,b)=>a.start-b.start);
const visible=comp=>comp.clips.filter(c=>!tracks(comp).find(t=>t.id===trackOf(c))?.hidden);
function transitions(comp,all=false){return tracks(comp).filter(t=>all||!t.hidden).flatMap(t=>clipsOn(comp,t.id).flatMap((right,i,rows)=>{const tr=right.transition,left=rows[i-1];if(!tr||!left||tr.from!==left.id||Math.abs(right.start-left.start-left.duration)>.5/comp.fps)return [];const half=Math.round(tr.duration*comp.fps/2)/comp.fps;return [{...tr,left,right,start:right.start-half,end:right.start+half}];}));}
function front(comp,time){for(const t of [...tracks(comp)].reverse()){if(t.hidden)continue;const effect=transitions(comp).find(tr=>trackOf(tr.right)===t.id&&time>=tr.start&&time<tr.end);if(effect)return {clip:clipsOn(comp,t.id).find(c=>time>=c.start&&time<c.start+c.duration)||effect.right,effect};const clip=clipsOn(comp,t.id).find(c=>time>=c.start&&time<c.start+c.duration);if(clip)return {clip,effect:null};}return {clip:null,effect:null};}

function checked(comp){
 const fps=comp.fps,rows=comp.clips.sort((a,b)=>a.start-b.start);
 if(rows.length>200)throw Error('画面最多 200 段，请减少片段后重试');
 if(comp.duration>21600)throw Error('成片不能超过 6 小时');
 for(let i=0;i<rows.length;i++){
  const c=rows[i],a=comp.assets.find(x=>x.id===c.asset);
  if(!a||a.kind==='audio'||c.start<0||frame(c.duration,fps)<1||c.start+c.duration>comp.duration+.001)throw Error('片段超出成片范围');
  if(a.kind==='video'&&(c.in<0||c.in+c.duration>a.duration+.001))throw Error('修剪超出源素材长度');
  if(!tracks(comp).some(t=>t.id===trackOf(c)))throw Error('片段引用了不存在的轨道');
  const previous=rows.slice(0,i).filter(row=>trackOf(row)===trackOf(c)).at(-1);
  if(previous&&frame(c.start,fps)<frame(previous.start+previous.duration,fps))throw Error('这里已有画面；请选择「插入排序」，或移到空白区间');
 }
 return comp;
}
function insert(original,clip,at,{ripple=true,splitId}={}){
 const comp=copy(original),fps=comp.fps,t=frame(at,fps),length=frame(clip.duration,fps),total=frame(comp.duration,fps);
 if(!Number.isFinite(at)||t<0||t>total||length<1)throw Error('请选择有效的画面落点');
 const rows=[];
 for(const c of comp.clips){
  const a=frame(c.start,fps),b=frame(c.start+c.duration,fps);
  if(trackOf(c)!==trackOf(clip)){rows.push(c);continue;}
  if(ripple&&a<t&&b>t){
   if(!splitId)throw Error('缺少分割片段编号');
   const image=comp.assets.find(x=>x.id===c.asset)?.kind==='image';
   const right={...copy(c),id:splitId,start:(t+length)/fps,in:image?0:c.in+(t-a)/fps,duration:(b-t)/fps};
   delete right.transition;c.duration=(t-a)/fps;rows.push(c,right);
  }else{if(ripple&&a>=t)c.start=(a+length)/fps;rows.push(c);}
 }
 rows.push({...copy(clip),start:t/fps,duration:length/fps});comp.clips=rows;
 comp.duration=(comp.tracks?Math.max(total,t+length,...rows.map(c=>frame(c.start+c.duration,fps))):Math.max(total+(ripple?length:0),t+length))/fps;
 return checked(comp);
}
function reorder(original,id,at){
 const comp=copy(original),fps=comp.fps,c=comp.clips.find(x=>x.id===id);
 if(!c)throw Error('片段已不存在，请重新选择');
 const start=frame(c.start,fps),length=frame(c.duration,fps),end=start+length,target=frame(at,fps);
 if(target>=start&&target<=end)return comp;
 const ident=trackOf(c);comp.clips=comp.clips.filter(x=>x.id!==id);
 for(const row of comp.clips)if(trackOf(row)===ident&&frame(row.start,fps)>=end)row.start=(frame(row.start,fps)-length)/fps;
 const point=target>=end?target-length:target;
 for(const row of comp.clips)if(trackOf(row)===ident&&frame(row.start,fps)>=point)row.start=(frame(row.start,fps)+length)/fps;
 c.start=point/fps;delete c.transition;comp.clips.push(c);return checked(comp);
}
function slot(comp,at,exclude,track){
 const t=Math.max(0,Math.min(comp.duration,at)),row=comp.clips.find(c=>c.id!==exclude&&trackOf(c)===(track||trackOf(comp.clips.find(x=>x.id===exclude)||{}))&&t>=c.start&&t<c.start+c.duration);
 return row?(t<row.start+row.duration/2?row.start:row.start+row.duration):frame(t,comp.fps)/comp.fps;
}
function segments(comp){const points=[...new Set([0,comp.duration,...visible(comp).flatMap(c=>[c.start,c.start+c.duration])])].sort((a,b)=>a-b);return points.slice(0,-1).map((start,i)=>({start,end:points[i+1],clip:front(comp,(start+points[i+1])/2).clip})).filter(row=>row.clip);}
const api={insert,reorder,slot,checked,trackOf,tracks,clipsOn,visible,transitions,front,segments};
if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.CWPictureEdits=api;
})(typeof window!=='undefined'?window:globalThis);
