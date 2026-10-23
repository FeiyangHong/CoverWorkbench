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

function getClientInfo()return {name='CW Voice Presets',author='CoverWorkbench',versionNumber=1,minEditorVersion=65537}end
local ranges={paramLoudness={-48,12},paramTension={-1,1},paramBreathiness={-1,1},paramGender={-1,1},paramToneShift={-400,400}}
function main()run(function()
  local p=guard();local e=SV:getMainEditor();local current=e:getCurrentGroup()
  local groups=e:getSelection():getSelectedGroups();if #groups==0 then groups={current}end
  local a=dialog('调声参数预设','保存：读取当前打开音符组的基础调声参数。\n应用：作用于 '..#groups..' 个已选音符组（未选组时为当前组）。\n保留自动化曲线、音符表情和声库；它们仍会影响声音。',{
    {name='mode',type='ComboBox',label='操作',choices={'保存当前组参数','应用已有参数'},default=0},
    txt('id','预设 ID（英文，可跨试点歌曲复用）','rose_soft'),
    check('modes','同时应用 SV2 声线模式：我确认源与目标使用同一声库',false)})
  if not a then return end
  local path=CWROOT..'data/sv-presets/'..hostMajor()..'_'..safeName(a.id)..'.tsv'
  if a.mode==0 then
    local v=current:getVoice();local rows={'CWVOICE\t1\t'..hostMajor()}
    for k,range in pairs(ranges)do local value=v[k];if finite(value)then rows[#rows+1]=hex(k)..'\t'..value end end
    for mode,params in pairs(v.vocalModeParams or {})do
      for _,key in ipairs({'pitch','timbre','pronunciation'})do local value=params[key]
        if finite(value)then rows[#rows+1]=hex('vocalModeParams')..'\t'..value..'\t'..hex(mode)..'\t'..hex(key)end
      end
    end
    if #rows==1 then error('当前组没有可保存的显式基础参数。先在声音面板设置参数。')end
    if writeData(path,rows)then SV:showMessageBox('调声预设已保存','已保存 '..(#rows-1)..' 个基础值。声库不在预设内；声线模式仅支持兼容的 SV2 声库。')end;return
  end
  local raw=read(path);if not raw then error('未找到此 SV 主版本的预设 '..a.id)end
  local lines={};for line in raw:gmatch('[^\r\n]+')do lines[#lines+1]=split(line)end
  if lines[1][1]~='CWVOICE'or lines[1][2]~='1'or tonumber(lines[1][3])~=hostMajor()then error('预设主版本不匹配')end
  local values={};local count=0
  for i=2,#lines do local row=lines[i];local k=unhex(row[1]);local value=tonumber(row[2])
    if not finite(value)then error('预设含无效数值')end
    if ranges[k]then
      if value<ranges[k][1]or value>ranges[k][2]then error('参数超出范围 '..k)end
      values[k]=value;count=count+1
    elseif k=='vocalModeParams'then
      local mode=unhex(row[3]);local key=unhex(row[4])
      if not ({pitch=true,timbre=true,pronunciation=true})[key]or value<0 or value>150 then error('声线模式无效')end
      if a.modes then values.vocalModeParams=values.vocalModeParams or {};values.vocalModeParams[mode]=values.vocalModeParams[mode]or{};values.vocalModeParams[mode][key]=value;count=count+1 end
    else error('未知参数 '..k)end
  end
  if count==0 then error('没有可应用的参数')end
  p:newUndoRecord();for _,r in ipairs(groups)do r:setVoice(values)end
  SV:showMessageBox('调声预设已应用',#groups..' 个音符组，'..count..' 个基础值。直接试听；Ctrl+Z 撤销。自动化曲线与音符覆盖值仍保留。')
end)end
