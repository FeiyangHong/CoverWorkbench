param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
if (-not $env:COVERWORKBENCH_PORT) { $env:COVERWORKBENCH_PORT = '8765' }
$port = [int]$env:COVERWORKBENCH_PORT
$url = 'http://127.0.0.1:' + $port + '/'
try {
    $health = Invoke-RestMethod -Uri ($url + 'api/health') -TimeoutSec 2
    if ($health.root -ne $projectRoot) { throw 'This port is occupied by another application.' }
    if (-not $NoBrowser) { Start-Process $url }
    Write-Output 'CoverWorkbench is already running.'
    exit 0
} catch {
    if ($_.Exception.Message -match 'occupied') { throw }
}
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $pythonExe = (& py -3 -c 'import sys; print(sys.executable)' | Select-Object -Last 1)
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $pythonExe = (& python -c 'import sys; print(sys.executable)' | Select-Object -Last 1)
    }
}
if (-not $pythonExe -or -not (Test-Path -LiteralPath $pythonExe)) { throw 'Run Setup.ps1 first; Python 3.11+ is required.' }
& $pythonExe (Join-Path $projectRoot 'tools\setup.py') | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Setup check failed.' }
$serverScript = Join-Path $projectRoot 'app\server.py'
$process = Start-Process -FilePath $pythonExe -ArgumentList @('"' + $serverScript + '"') -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $projectRoot 'logs\server.log') -RedirectStandardError (Join-Path $projectRoot 'logs\server-error.log') -PassThru
$ready = $false
$serverProcessId = $null
for ($attempt=0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Milliseconds 200
    try {
        $health = Invoke-RestMethod -Uri ($url + 'api/health') -TimeoutSec 1
        # Windows venv python.exe can redirect into a child interpreter.
        $candidate = Get-CimInstance Win32_Process -Filter ("ProcessId = " + [int]$health.pid)
        if ($health.root -eq $projectRoot -and $candidate -and
            ($candidate.ProcessId -eq $process.Id -or $candidate.ParentProcessId -eq $process.Id) -and
            $candidate.CommandLine.Contains($serverScript)) {
            $serverProcessId = [int]$health.pid
            $ready=$true
            break
        }
    } catch {}
}
if (-not $ready) {
    $owned = Get-CimInstance Win32_Process | Where-Object {
        ($_.ProcessId -eq $process.Id -or $_.ParentProcessId -eq $process.Id) -and
        $_.CommandLine -and $_.CommandLine.Contains($serverScript)
    }
    $owned | ForEach-Object { Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }
    throw 'Server startup failed. See logs\server-error.log.'
}
$serverProcessId | Set-Content -LiteralPath (Join-Path $projectRoot 'runtime\server.pid') -Encoding ascii
if (-not $NoBrowser) { Start-Process $url }
Write-Output ('CoverWorkbench is ready: ' + $url)
