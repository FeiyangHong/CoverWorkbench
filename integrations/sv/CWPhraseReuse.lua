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

function getClientInfo()return {name='CW Phrase Reuse',author='CoverWorkbench',versionNumber=1,minEditorVersion=65537}end
function main()run(function()
  local p,pid=guard();local ns,r=selected(p)
  local a=dialog('重复乐句复用 · '..#ns..' 个音符','先选择已修好的乐句并保存，再选择目标乐句并应用同一 ID。\n应用保留目标音符时间、音高曲线、逐音符表情和声库。仅勾选的字段会改变。',{
    {name='mode',type='ComboBox',label='操作',choices={'保存所选乐句','应用已有乐句'},default=0},
    txt('id','本曲乐句 ID（英文）','chorus_01'),check('lyrics','复制歌词',true),
    check('phones','复制自定义音素（需同语言 / 音素集）',false),check('pitch','复制基础音高',false),
    txt('transpose','基础音高移调（半音，仅复制音高时有效）','0'),
    check('rhythm','允许不同节奏（默认要求相对起点和时值一致）',false)})
  if not a then return end
  local path=CWROOT..'data/sv-phrases/'..pid..'_'..safeName(a.id)..'.tsv'
  if a.mode==0 then
    local rows={'CWPHRASE\t1\t'..pid..'\t'..hostMajor()}
    local first=ns[1]:getOnset()
    for _,n in ipairs(ns)do rows[#rows+1]=table.concat({n:getOnset()-first,n:getDuration(),n:getPitch()+r:getPitchOffset(),hex(n:getLyrics()),hex(n:getPhonemes())},'\t')end
    if writeData(path,rows)then SV:showMessageBox('乐句已保存',#ns..' 个音符。目标处选择同样数量的音符，再应用 '..a.id..'。')end;return
  end
  local raw=read(path);if not raw then error('没有找到本曲乐句预设 '..a.id)end
  local rows={};for line in raw:gmatch('[^\r\n]+')do rows[#rows+1]=split(line)end
  if rows[1][1]~='CWPHRASE'or rows[1][2]~='1'or rows[1][3]~=pid or tonumber(rows[1][4])~=hostMajor()then error('预设格式、项目或 SV 主版本不匹配')end
  if #rows-1~=#ns then error('音符数量不一致，没有修改：源 '..(#rows-1)..' / 目标 '..#ns)end
  local shift=tonumber(a.transpose);if not finite(shift)or shift%1~=0 or math.abs(shift)>48 then error('移调必须是 ±48 内的整数')end
  local edits={};local first=ns[1]:getOnset()
  for i,n in ipairs(ns)do
    local row=rows[i+1];local onset,dur,pitch=tonumber(row[1]),tonumber(row[2]),tonumber(row[3])
    if not finite(onset)or not finite(dur)or dur<=0 or not finite(pitch)or pitch%1~=0 then error('乐句预设含无效音符')end
    if not a.rhythm and (math.abs(onset-(n:getOnset()-first))>705600000/128 or math.abs(dur-n:getDuration())>705600000/128)then error('第 '..i..' 音符节奏不同，没有修改。确认后可显式允许不同节奏。')end
    local dest=pitch+shift-r:getPitchOffset()
    if a.pitch and (dest<0 or dest>127)then error('移调后音高超出 0–127')end
    local lyric=unhex(row[4]);local phone=unhex(row[5]);if #lyric>800 or #phone>2000 then error('预设文本过长')end
    edits[i]={pitch=dest,lyrics=lyric,phones=phone}
  end
  if not a.lyrics and not a.phones and not a.pitch then error('请至少选择一个复制字段')end
  p:newUndoRecord()
  for i,n in ipairs(ns)do local e=edits[i]
    if a.lyrics and n:getLyrics()~=e.lyrics then n:setLyrics(e.lyrics);if not a.phones then n:setPhonemes('')end end
    if a.phones then n:setPhonemes(e.phones)end
    if a.pitch then n:setPitch(e.pitch)end
  end
  SV:showMessageBox('乐句复用完成','已处理 '..#ns..' 个所选音符。时间和曲线保留；请试听目标段落，Ctrl+Z 撤销。')
end)end
