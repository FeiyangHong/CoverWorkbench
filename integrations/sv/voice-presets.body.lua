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
