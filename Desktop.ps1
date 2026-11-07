param([string]$Workspace = $PSScriptRoot)
$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run Setup.ps1 -WithDesktop first.' }
Start-Process -FilePath $python -ArgumentList @('"' + (Join-Path $PSScriptRoot 'app\desktop_main.py') + '"','--workspace','"' + $Workspace + '"') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
