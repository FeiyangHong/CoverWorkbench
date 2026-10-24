param()
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    $pythonExe = (& python -c 'import sys; print(sys.executable)' | Select-Object -Last 1)
}
if (-not $pythonExe) { throw 'Run Setup.ps1 first.' }
& $pythonExe -m pip install -r (Join-Path $PSScriptRoot 'requirements-native-audio.txt')
if ($LASTEXITCODE -ne 0) { throw 'Optional audio engine installation failed.' }
Write-Output 'Native audio engine installed. Refresh the mixing guide. Install and authorize FabFilter VST3 separately.'
