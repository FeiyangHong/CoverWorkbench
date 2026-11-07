param([string]$Executable = '',[string]$Workspace = (Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not $Executable) { $Executable = Join-Path $root 'dist\desktop\CoverWorkbench\CoverWorkbench.exe' }
$exe = [IO.Path]::GetFullPath($Executable)
if (-not (Test-Path -LiteralPath $exe)) { throw 'Build or select CoverWorkbench.exe first.' }
$path = Join-Path ([Environment]::GetFolderPath('Desktop')) 'CoverWorkbench Desktop.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($path)
if ((Test-Path -LiteralPath $path) -and $shortcut.TargetPath -ne $exe) { throw 'This desktop shortcut has another target; it was not replaced.' }
$shortcut.TargetPath = $exe
$shortcut.Arguments = '--workspace "' + [IO.Path]::GetFullPath($Workspace) + '"'
$shortcut.WorkingDirectory = $root
$shortcut.IconLocation = $exe + ',0'
$shortcut.Description = 'CoverWorkbench Desktop - shared local music and video workspace'
$shortcut.Save()
Write-Output $path
