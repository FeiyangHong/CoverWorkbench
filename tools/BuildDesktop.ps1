param([string]$PythonExe = 'python',[string]$Output = '')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$buildEnv = Join-Path $root 'work\Desktop Build Env'
$buildPython = Join-Path $buildEnv 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $buildPython)) {
    & $PythonExe -m venv $buildEnv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the desktop build environment.' }
}
& $buildPython -m pip install -r (Join-Path $root 'requirements-desktop.txt') yt-dlp numpy scipy
if ($LASTEXITCODE -ne 0) { throw 'Desktop build dependencies failed to install.' }
$argsList = @((Join-Path $root 'tools\build_desktop.py'))
if ($Output) { $argsList += @('--output',$Output) }
& $buildPython @argsList
if ($LASTEXITCODE -ne 0) { throw 'Desktop build failed.' }
