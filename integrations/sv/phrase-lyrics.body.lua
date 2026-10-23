function getClientInfo()return {name='CW Phrase Lyrics',author='CoverWorkbench',versionNumber=1,minEditorVersion=65537}end
function main()run(function()
  local p=guard();local ns=selected(p);local defaults={}
  for _,n in ipairs(ns)do defaults[#defaults+1]=n:getLyrics()end
  local a=dialog('整段填词 · '..#ns..' 个音符','按音符顺序填入，一音符一项，空白分隔。\n延音请手动放入 - 或 +；假名拆分只是素材，不能保证对应旋律。\n只修改所选音符的歌词，可在 SV 撤销。',{
    {name='lyrics',type='TextArea',label='歌词单位（空格分隔）',height=140,default=table.concat(defaults,' ')},
    check('clear','歌词改变时清除旧自定义音素（建议）',true)})
  if not a then return end
  local tokens={};for token in a.lyrics:gmatch('%S+')do
    if #token>800 then error('单项歌词过长')end;tokens[#tokens+1]=token
  end
  if #tokens~=#ns then error('没有修改：选择了 '..#ns..' 个音符，但输入 '..#tokens..' 项。请修正数量。')end
  -- Validate the full selection before creating the undo step.
  local changed=0;for i,n in ipairs(ns)do if n:getLyrics()~=tokens[i]then changed=changed+1 end end
  if changed>0 then
    p:newUndoRecord()
    for i,n in ipairs(ns)do if n:getLyrics()~=tokens[i]then n:setLyrics(tokens[i]);if a.clear then n:setPhonemes('')end end end
  end
  SV:showMessageBox('整段填词完成','修改 '..changed..' 个音符。直接在 SV 试听；Ctrl+Z 撤销，Ctrl+S 保存副本。')
end)end
