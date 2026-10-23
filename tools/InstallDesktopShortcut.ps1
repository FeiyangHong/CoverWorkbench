param([ValidateSet('cw-signature','cw-vocal','cw-studio')][string]$Icon = 'cw-signature')
$ErrorActionPreference = 'Stop'
$workbenchRoot = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $workbenchRoot 'Start.vbs'
$iconFile = Join-Path $workbenchRoot ('assets\icons\' + $Icon + '.ico')
if (-not (Test-Path -LiteralPath $launcher)) { throw 'Start.vbs is missing.' }
if (-not (Test-Path -LiteralPath $iconFile)) { throw 'Icon is missing.' }
$desktopPath = [Environment]::GetFolderPath('Desktop')
$linkPath = Join-Path $desktopPath 'CoverWorkbench.lnk'
$shellObject = New-Object -ComObject WScript.Shell
if (Test-Path -LiteralPath $linkPath) {
    $existing = $shellObject.CreateShortcut($linkPath)
    if ($existing.Arguments -ne ('"' + $launcher + '"')) {
        throw 'A different CoverWorkbench shortcut already exists; it was not changed.'
    }
}
$link = $shellObject.CreateShortcut($linkPath)
$link.TargetPath = Join-Path $env:SystemRoot 'System32\wscript.exe'
$link.Arguments = '"' + $launcher + '"'
$link.WorkingDirectory = $workbenchRoot
$link.IconLocation = $iconFile + ',0'
$link.Description = 'CoverWorkbench - local cover production studio'
$link.WindowStyle = 7
$link.Save()
Write-Output $linkPath
