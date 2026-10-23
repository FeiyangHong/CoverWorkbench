-- Embedded into each installed script; no dynamic code is loaded from disk.
local CWROOT="__CW_ROOT__/"
local function hex(s)return (s:gsub('.',function(c)return string.format('%02x',c:byte())end))end
local function unhex(s)
  if #s%2~=0 or s:find('[^%x]') then error('Invalid encoded data')end
  return (s:gsub('%x%x',function(c)return string.char(tonumber(c,16))end))
end
local function split(s)local t={};for v in (s..'\t'):gmatch('(.-)\t')do t[#t+1]=v end;return t end
local function finite(n)return type(n)=='number' and n==n and math.abs(n)<math.huge end
local function norm(s)return s:gsub('\\','/'):lower()end
local function read(path)local f=io.open(path,'rb');if not f then return nil end;local s=f:read('*a');f:close();return s end
local function hostMajor()return math.floor(SV:getHostInfo().hostVersionNumber/65536)end
local function guard()
  local p=SV:getProject();local manifest=read(CWROOT..'runtime/sv-live/manifest.tsv')or''
  for line in manifest:gmatch('[^\r\n]+')do local c=split(line)
    if norm(p:getFileName())==norm(unhex(c[2]))then return p,c[1]end
  end
  error('只允许已注册的 working/sv 或 working/sv2 工作副本。请打开工作副本；原工程不允许修改。')
end
local function selected(p)
  local e=SV:getMainEditor();local r=e:getCurrentGroup();local ns=e:getSelection():getSelectedNotes()
  if #ns==0 then error('请先在当前音符组中选择需要处理的音符。')end
  local id=r:getTarget():getUUID()
  for _,n in ipairs(ns)do if n:getParent():getUUID()~=id then error('选择必须位于同一个当前音符组。')end end
  table.sort(ns,function(a,b)return a:getOnset()<b:getOnset()end)
  for i=2,#ns do if ns[i]:getOnset()==ns[i-1]:getOnset()then error('存在同时起始的音符，无法确定歌词顺序。')end end
  local refs=0
  for ti=1,p:getNumTracks()do local t=p:getTrack(ti)
    for ri=1,t:getNumGroups()do if t:getGroupReference(ri):getTarget():getUUID()==id then refs=refs+1 end end
  end
  if refs>1 then error('当前是共享音符组。请先在 SV 中克隆为独立音符组，再批量修改。')end
  return ns,r
end
local function dialog(title,message,widgets)
  local answer=SV:showCustomDialog{title=title,message=message,buttons='YesNoCancel',widgets=widgets}
  if answer.status~='Yes'then return nil end;return answer.answers
end
local function txt(name,label,value)return {name=name,type='TextBox',label=label,default=value}end
local function check(name,label,value)return {name=name,type='CheckBox',text=label,default=value}end
local function safeName(s)
  if not s or not s:match('^[A-Za-z0-9][A-Za-z0-9_-]*$')or #s>48 then error('预设 ID 请使用 1–48 位英文字母、数字、下划线或连字符。')end
  return s
end
local function writeData(path,rows)
  if read(path)then
    if not SV:showOkCancelBox('覆盖已有预设？','只覆盖此预设数据；工程不会保存或重写。\n'..path)then return false end
  end
  local temp=path..'.tmp';local f,err=io.open(temp,'wb');if not f then error(err)end
  f:write(table.concat(rows,'\n')..'\n');f:close()
  local backup=path..'.bak'
  if read(path)then
    os.remove(backup);local ok,e=os.rename(path,backup);if not ok then error(e)end
  end
  local ok,e=os.rename(temp,path)
  if not ok then if read(backup)then os.rename(backup,path)end;error(e)end
  return true
end
local function run(fn)
  local ok,err=pcall(fn)
  if not ok then SV:showMessageBox('CoverWorkbench · 操作未完成',tostring(err))end
  SV:finish()
end
