/* Session-only, bounded subtitle history. No project metadata or media is stored. */
((root)=>{
'use strict';
const encode=value=>JSON.stringify(value,(_,v)=>typeof v==='number'&&!Number.isFinite(v)?{__cwNumber:String(v)}:v);
const decode=value=>JSON.parse(value,(_,v)=>v&&typeof v==='object'&&Object.keys(v).length===1&&['NaN','Infinity','-Infinity'].includes(v.__cwNumber)?Number(v.__cwNumber):v);
class SubtitleHistory{
 constructor({limit=100,bytes=16*1024*1024,onchange=()=>{}}={}){this.limit=limit;this.bytes=bytes;this.onchange=onchange;this.reset({});}
 reset(value){this.current=encode(value);this.past=[];this.future=[];this.transaction=null;this.breakGroup();this.notify();}
 notify(){this.onchange(this.status());}
 status(){const pending=!!this.transaction&&this.transaction.before!==this.current;return {undo:this.past.length+Number(pending),redo:pending?0:this.future.length,undoLabel:(pending?this.transaction.label:this.past.at(-1)?.label)||'',redoLabel:pending?'':this.future.at(-1)?.label||''};}
 breakGroup(){this.group=null;}
 trim(){let size=[...this.past,...this.future].reduce((n,e)=>n+2*(e.before.length+e.after.length),0);while(this.past.length>1&&(this.past.length+this.future.length>this.limit||size>this.bytes)){const e=this.past.shift();size-=2*(e.before.length+e.after.length);}}
 record(value,{key='',label='编辑字幕',merge=false,now=Date.now()}={}){
  const next=encode(value);if(next===this.current)return;
  if(this.transaction){this.current=next;this.notify();return;}
  const last=this.past.at(-1);
  if(merge&&key&&this.group?.key===key&&now-this.group.time<800&&last&&last.after===this.current&&!this.future.length){last.after=next;if(last.before===last.after)this.past.pop();}
  else this.past.push({before:this.current,after:next,label});
  this.current=next;this.future=[];this.group=merge&&key?{key,time:now}:null;this.trim();this.notify();
 }
 begin(label='编辑字幕'){this.commit();this.breakGroup();this.transaction={before:this.current,label};this.notify();}
 commit(){if(!this.transaction)return;const {before,label}=this.transaction;this.transaction=null;if(before!==this.current){this.past.push({before,after:this.current,label});this.future=[];this.trim();}this.breakGroup();this.notify();}
 undo(){this.commit();const entry=this.past.pop();if(!entry)return null;this.future.push(entry);this.current=entry.before;this.breakGroup();this.notify();return {value:decode(this.current),label:entry.label};}
 redo(){this.commit();const entry=this.future.pop();if(!entry)return null;this.past.push(entry);this.current=entry.after;this.breakGroup();this.notify();return {value:decode(this.current),label:entry.label};}
 // Saving may materialize one audio-offset delta into every subtitle timestamp.
 // Apply that same coordinate change to history, rather than shifting again on undo.
 rebase(transform){const convert=s=>encode(transform(decode(s)));this.current=convert(this.current);for(const entry of [...this.past,...this.future]){entry.before=convert(entry.before);entry.after=convert(entry.after);}if(this.transaction)this.transaction.before=convert(this.transaction.before);this.trim();this.notify();}
 sync(value){const previous=this.current;this.current=encode(value);const last=this.past.at(-1),next=this.future.at(-1);if(last?.after===previous)last.after=this.current;if(next?.before===previous)next.before=this.current;this.breakGroup();this.notify();}
}
if(typeof module!=='undefined'&&module.exports)module.exports=SubtitleHistory;else root.CWSubtitleHistory=SubtitleHistory;
})(typeof window!=='undefined'?window:globalThis);
