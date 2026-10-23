-- Data-only file bridge. Never evaluates incoming script text.
local ROOT="__CW_ROOT__/runtime/sv-live/"
local allowed={}
local auditionEnd=nil
local auditionStart=nil
local auditionLoop=false
local ticks=0
local cachedRows={}
local function audition(pb,c)
  auditionStart=tonumber(c[14]);auditionEnd=tonumber(c[15]);auditionLoop=c[16]~='0'
  pb:pause()
  -- play() can retain a previous native loop. A padded native range lets
  -- the timer stop at B before the native loop wraps, including resume.
  pb:loop(auditionStart,auditionLoop and auditionEnd or auditionEnd+1)
  pb:seek(tonumber(c[17]) or auditionStart)
end
local session,last,status,message="","","ready",""
function getClientInfo() return {name="CoverWorkbench Live",author="CoverWorkbench",versionNumber=3,minEditorVersion=65537} end
local function unhex(s) return (s:gsub('%x%x',function(v)return string.char(tonumber(v,16))end)) end
local function norm(s) return s:gsub('\\','/'):lower() end
local function read(p) local f=io.open(ROOT..p,'rb');if not f then return nil end;local t=f:read('*a');f:close();return t end
local function fields(s) local out={}; for v in (s..'\t'):gmatch('(.-)\t') do out[#out+1]=v end;return out end
local function json(v)
  local t=type(v)
  if t=='string' then return '"'..v:gsub('[%z\1-\31\\"]',function(c) local x={['"']='\\"',['\\']='\\\\',['\n']='\\n',['\r']='\\r',['\t']='\\t'};return x[c] or string.format('\\u%04x',c:byte()) end)..'"' end
  if t=='number' or t=='boolean' then return tostring(v) end
  if t=='table' then
    local out={}; if #v>0 then for i,x in ipairs(v) do out[#out+1]=json(x) end;return '['..table.concat(out,',')..']' end
    for k,x in pairs(v) do out[#out+1]=json(k)..':'..json(x) end;return '{'..table.concat(out,',')..'}'
  end
  return 'null'
end
local function scan(p)
  local rows={};local refs={};local axis=p:getTimeAxis()
  for ti=1,p:getNumTracks() do
    local t=p:getTrack(ti)
    for ri=1,t:getNumGroups() do
      local r=t:getGroupReference(ri);local g=r:getTarget();local id=g:getUUID();refs[id]=(refs[id] or 0)+1
      for ni=1,g:getNumNotes() do
        local n=g:getNote(ni);local onset=n:getOnset();local duration=n:getDuration();local offset=r:getTimeOffset()
        rows[#rows+1]={track=ti-1,uuid=id,offset=offset,onset=onset,duration=duration,index=ni-1,pitch=n:getPitch()+r:getPitchOffset(),lyrics=n:getLyrics(),phonemes=n:getPhonemes(),start=axis:getSecondsFromBlick(onset+offset),['end']=axis:getSecondsFromBlick(onset+offset+duration)}
      end
    end
  end
  return rows,refs
end
local function apply(p,c)
  -- seq, session, project, verb, track, uuid, offset, onset, duration, expectedPitch, expectedLyrics, pitch, lyrics, start, end
  if #c<4 or c[2]~=session then error('Bridge session changed; reconnect.') end
  if unhex(c[3])~=allowed[norm(p:getFileName())] then error('Open the selected pilot working copy.') end
  local pb=SV:getPlayback()
  if c[4]=='pause' then pb:pause();return end
  if c[4]=='seek' then pb:pause();pb:seek(tonumber(c[17]));auditionEnd=nil;return end
  if c[4]=='gain' then p:newUndoRecord();p:getTrack(tonumber(c[5])+1):getMixer():setGainDecibel(tonumber(c[18]));return end
  if c[4]=='disconnect' then status='disconnected';pb:pause();return end
  if c[4]=='play' then audition(pb,c);return end
  if c[4]~='apply' then error('Unknown bridge command.') end
  local t=p:getTrack(tonumber(c[5])+1);local target=nil;local shift=0
  local _,refs=scan(p)
  if (refs[unhex(c[6])] or 0)>1 then error('Shared group: edit in SV to avoid changing other instances.') end
  for ri=1,t:getNumGroups() do
    local r=t:getGroupReference(ri);local g=r:getTarget()
    if g:getUUID()==unhex(c[6]) and r:getTimeOffset()==tonumber(c[7]) then
      for ni=1,g:getNumNotes() do
        local n=g:getNote(ni)
        if n:getOnset()==tonumber(c[8]) and n:getDuration()==tonumber(c[9]) then
          if target then error('Ambiguous note address.') end;target=n;shift=r:getPitchOffset()
        end
      end
    end
  end
  if not target then error('Note moved or group changed; refresh from SV.') end
  if target:getPitch()+shift~=tonumber(c[10]) or target:getLyrics()~=unhex(c[11]) then error('Note was changed in SV; refresh before applying.') end
  local pitch=tonumber(c[12]);local text=unhex(c[13]);if not pitch or pitch%1~=0 or pitch-shift<0 or pitch-shift>127 or #text>800 then error('Invalid note values.') end
  if target:getPitch()+shift~=pitch or target:getLyrics()~=text then
    p:newUndoRecord()
    if target:getLyrics()~=text then target:setLyrics(text);target:setPhonemes('') end
    target:setPitch(pitch-shift)
  end
  audition(pb,c)
end
local function tick()
  local p=SV:getProject();local path=p:getFileName();local pid=allowed[norm(path)] or ''
  local changed=false
  local stoppedAtEnd=false
  local pb=SV:getPlayback()
  if auditionEnd and not auditionLoop and pb:getStatus()~='stopped' and pb:getPlayhead()>=auditionEnd then pb:pause();pb:seek(auditionEnd);stoppedAtEnd=true end
  local cmd=read('command.tsv')
  if cmd then
    local c=fields(cmd:gsub('[\r\n]+$',''))
    if c[1] and c[1]~=last then
      changed=true;last=c[1];local ok,err=pcall(function() apply(p,c) end);status=ok and (status=='disconnected' and status or 'applied') or 'error';message=ok and '' or tostring(err)
    end
  end
  ticks=ticks+1
  if ticks%5~=1 and not changed and not stoppedAtEnd then SV:setTimeout(100,tick);return end
  if ticks%5==1 or changed then cachedRows=pid~='' and scan(p) or {} end
  local rows=cachedRows
  local tracks={}
  if pid~='' then for ti=1,p:getNumTracks() do local t=p:getTrack(ti);local ok,m=pcall(function() return t:getMixer() end);if ok and m then tracks[#tracks+1]={track=ti-1,name=t:getName(),gain=m:getGainDecibel(),muted=m:isMuted(),solo=m:isSolo(),gainSupported=true} else tracks[#tracks+1]={track=ti-1,name=t:getName(),gainSupported=false} end end end
  local snap={protocol=3,tracks=tracks,auditionStart=auditionStart,auditionEnd=auditionEnd,auditionLoop=auditionLoop,session=session,updatedAt=os.time(),pid=pid,path=path,sequence=last,status=status,message=message,nativePlayback=SV:getPlayback():getStatus(),playback=(not auditionLoop and auditionEnd and SV:getPlayback():getStatus()~='stopped') and 'playing' or SV:getPlayback():getStatus(),playhead=SV:getPlayback():getPlayhead(),notes=rows}
  local f=io.open(ROOT..'status.tmp','wb');if f then f:write(json(snap));f:close();os.remove(ROOT..'status.json');os.rename(ROOT..'status.tmp',ROOT..'status.json') end
  if status=='disconnected' then SV:finish();return end
  SV:setTimeout(100,tick)
end
function main()
  local prior=read('status.json');local recent=prior and tonumber(prior:match('"updatedAt":(%d+)')) or 0
  if recent and os.time()-recent<4 and not prior:find('"status":"disconnected"',1,true) then SV:showMessageBox('CoverWorkbench','A live bridge is already running. Disconnect it in the workbench first.');SV:finish();return end
  local m=read('manifest.tsv') or ''
  for line in m:gmatch('[^\r\n]+') do local c=fields(line);allowed[norm(unhex(c[2]))]=c[1] end
  if not allowed[norm(SV:getProject():getFileName())] then SV:showMessageBox('CoverWorkbench','Open a pilot working SVP first. Original projects are excluded.');SV:finish();return end
  session=tostring(os.time())..'-'..tostring(math.random(100000,999999));last=read('command.tsv') and fields(read('command.tsv'))[1] or ''
  tick()
end
