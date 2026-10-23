$ErrorActionPreference = 'Stop'
$pidFile = Join-Path $PSScriptRoot 'runtime\server.pid'
if (-not (Test-Path -LiteralPath $pidFile)) { Write-Output 'No managed server PID was recorded.'; exit 0 }
$serverPid = [int](Get-Content -LiteralPath $pidFile)
$process = Get-CimInstance Win32_Process -Filter "ProcessId = $serverPid"
$expectedScript = Join-Path $PSScriptRoot 'app\server.py'
if ($process -and $process.CommandLine.Contains($expectedScript)) {
    Stop-Process -Id $serverPid
    Remove-Item -LiteralPath $pidFile
    Write-Output 'CoverWorkbench stopped.'
} elseif ($process) { throw 'Recorded PID belongs to another process. It was not stopped.' }
