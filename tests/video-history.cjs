/* Real editing state transitions, including transaction and save-coordinate boundaries. */
const assert=require('node:assert/strict'),History=require('../app/static/video/history.js');
const initial={cues:[{id:'A',start:1,end:3,original:'Before',translation:'Text',translationTiming:{start:1.5,end:3.5}}],styles:{original:{size:40}},subtitleShift:0};
let h=new History(),state=structuredClone(initial);h.reset(state);
h.begin('drag');for(let i=1;i<=30;i++){state.cues[0].start=1+i/100;h.record(state);}h.commit();
assert.equal(h.status().undo,1);assert.deepEqual(h.undo().value,initial);assert.deepEqual(h.redo().value,state);
h.begin('cancel');const before=structuredClone(state);state.cues[0].original='temporary';h.record(state);h.record(before);h.commit();assert.equal(h.status().undo,1);
h.undo();h.begin('cancel after undo');state=structuredClone(initial);state.cues[0].original='temporary';h.record(state);h.record(initial);h.commit();assert.equal(h.status().redo,1);h.redo();
h.reset(initial);state=structuredClone(initial);for(const [i,text] of ['A','AB','ABC'].entries()){state.cues[0].original=text;h.record(state,{key:'A:original',merge:true,now:100+i*100});}assert.equal(h.status().undo,1);assert.equal(h.undo().value.cues[0].original,'Before');h.redo();h.undo();state=structuredClone(initial);state.subtitleShift=1;h.record(state);assert.equal(h.status().redo,0);
h.reset(initial);state=structuredClone(initial);state.cues[0].end=4;h.record(state);h.sync(state);assert.deepEqual(h.undo().value,initial);h.redo();
h.rebase(s=>{for(const r of s.cues){r.start+=2;r.end+=2;if(r.translationTiming){r.translationTiming.start+=2;r.translationTiming.end+=2;}}return s;});
assert.equal(h.undo().value.cues[0].start,3);assert.equal(h.redo().value.cues[0].translationTiming.start,3.5);
h.reset(initial);state=structuredClone(initial);state.cues[0].start=NaN;h.record(state);h.undo();assert.ok(Number.isNaN(h.redo().value.cues[0].start));
h=new History({limit:3,bytes:1024});h.reset({n:0});for(let n=1;n<=20;n++)h.record({n});assert.equal(h.status().undo,3);h.undo();h.undo();h.undo();assert.equal(h.undo(),null);h.reset(initial);assert.equal(h.status().redo,0);
console.log('PASS: one-step transactions, canceled edit/redo preservation, text coalescing, branching, save checkpoints, offset rebasing, invalid drafts and bounded history');
