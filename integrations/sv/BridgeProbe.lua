function getClientInfo()
  return {name="CoverWorkbench Bridge Probe", author="CoverWorkbench", versionNumber=1, minEditorVersion=65537}
end
function main()
  local ok, err = pcall(function()
    local base=os.getenv("COVERWORKBENCH_ROOT")
    if not base then error("Set COVERWORKBENCH_ROOT before using this developer probe") end
    local f=assert(io.open(base.."/runtime/bridge-probe.txt", "w"))
    f:write(SV:getProject():getFileName(), "\n", SV:getHostInfo().hostName or "SV", "\n")
    f:close()
  end)
  SV:showMessageBox("CoverWorkbench", ok and "File bridge available." or tostring(err))
  SV:finish()
end
