param([string]$PythonExe = '', [switch]$WithLyrics)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
if (-not $PythonExe) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $PythonExe = (& py -3 -c 'import sys; print(sys.executable)' | Select-Object -Last 1)
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $PythonExe = (& python -c 'import sys; print(sys.executable)' | Select-Object -Last 1)
    }
}
if (-not $PythonExe -or -not (Test-Path -LiteralPath $PythonExe)) { throw 'Install Python 3.11+ or pass -PythonExe with its absolute path.' }
& $PythonExe -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ required"'
if ($LASTEXITCODE -ne 0) { throw 'Python version check failed.' }
$venvPython = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    & $PythonExe -m venv (Join-Path $root '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the virtual environment.' }
}
if ($WithLyrics) {
    & $venvPython -m pip install -r (Join-Path $root 'requirements-lyrics.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Optional lyric dependencies failed to install.' }
}
& $venvPython (Join-Path $root 'tools\setup.py')
if ($LASTEXITCODE -ne 0) { throw 'Setup failed.' }
Write-Output 'Ready. Run .\Start.ps1 or double-click Start.vbs.'
