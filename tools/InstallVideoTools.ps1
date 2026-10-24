param()
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    $pythonExe = (& python -c 'import sys; print(sys.executable)' | Select-Object -Last 1)
}
if (-not $pythonExe) { throw 'Run Setup.ps1 first.' }
& $pythonExe -m pip install -r (Join-Path $PSScriptRoot 'requirements-video.txt')
if ($LASTEXITCODE -ne 0) { throw 'Optional video tools installation failed.' }
Write-Output 'Video tools installed. Configure FFmpeg and FFprobe in Environment settings, then refresh Video Studio.'
