/* Backward-compatible shared times with optional per-language overrides. */
(() => {
'use strict';
const languages=['original','translation'];
function get(row,key){return row[key+'Timing']||{start:row.start,end:row.end};}
function set(row,key,range){const value={start:Math.round(range.start*1000)/1000,end:Math.round(range.end*1000)/1000};if(value.start===row.start&&value.end===row.end)delete row[key+'Timing'];else row[key+'Timing']=value;}
function shift(row,delta){row.start+=delta;row.end+=delta;for(const key of languages)if(row[key+'Timing'])set(row,key,{start:row[key+'Timing'].start+delta,end:row[key+'Timing'].end+delta});}
function retime(row,start,end,key='original'){const reference=get(row,key),ds=start-reference.start,de=end-reference.end,ranges=Object.fromEntries(languages.map(k=>[k,{...get(row,k)}]));row.start+=ds;row.end+=de;for(const k of languages)set(row,k,{start:ranges[k].start+ds,end:ranges[k].end+de});}
function bounds(row){const ranges=languages.filter(k=>row[k]).map(k=>get(row,k));return ranges.length?{start:Math.min(...ranges.map(r=>r.start)),end:Math.max(...ranges.map(r=>r.end))}:{start:row.start,end:row.end};}
window.CWCaptionTiming={languages,get,set,shift,retime,bounds};
})();
