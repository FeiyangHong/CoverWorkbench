Set launcher = CreateObject("WScript.Shell")
Set filesystem = CreateObject("Scripting.FileSystemObject")
root = filesystem.GetParentFolderName(WScript.ScriptFullName)
launcher.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & root & "\Desktop.ps1""", 0, False
