param(
    [ValidateSet('status','apply')][string]$Mode = 'status',
    [ValidateSet('cw-signature','cw-vocal','cw-studio')][string]$Icon = 'cw-signature'
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$workbenchRoot = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $workbenchRoot 'Start.vbs'
$desktopPath = [Environment]::GetFolderPath('Desktop')
$linkPath = Join-Path $desktopPath 'CoverWorkbench.lnk'
$exists = Test-Path -LiteralPath $linkPath
$shellObject = New-Object -ComObject WScript.Shell
$link = $shellObject.CreateShortcut($linkPath)
$owned = (-not $exists) -or (($link.Arguments -eq ('"' + $launcher + '"')) -and ([IO.Path]::GetFileName($link.TargetPath) -ieq 'wscript.exe'))
if ($Mode -eq 'apply') {
    if (-not $owned) { throw 'Desktop shortcut belongs to a different target; it was not changed.' }
    $iconFile = Join-Path $workbenchRoot ('assets\icons\' + $Icon + '.ico')
    if (-not (Test-Path -LiteralPath $iconFile)) { throw 'Icon file is missing.' }
    if (-not (Test-Path -LiteralPath $launcher)) { throw 'Start.vbs is missing.' }
    if (-not $exists) {
        $link.TargetPath = Join-Path $env:SystemRoot 'System32\wscript.exe'
        $link.Arguments = '"' + $launcher + '"'
        $link.WorkingDirectory = $workbenchRoot
        $link.Description = 'CoverWorkbench - local cover production studio'
        $link.WindowStyle = 7
    }
    $link.IconLocation = $iconFile + ',0'
    $link.Save()
    $exists = $true
    Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public class CWDesktopIconRefresh { [DllImport("shell32.dll", CharSet=CharSet.Unicode)] public static extern void SHChangeNotify(uint eventId, uint flags, string path, IntPtr unused); }'
    [CWDesktopIconRefresh]::SHChangeNotify(0x2000,0x5,$linkPath,[IntPtr]::Zero)
}
$selected = $null
foreach ($candidate in @('cw-signature','cw-vocal','cw-studio')) {
    $expectedIcon = (Join-Path $workbenchRoot ('assets\icons\' + $candidate + '.ico')) + ',0'
    if ($exists -and $link.IconLocation -ieq $expectedIcon) { $selected = $candidate }
}
[pscustomobject]@{selected=$selected;shortcutExists=[bool]$exists;canApply=[bool]$owned;shortcut=$linkPath;iconLocation=$link.IconLocation} | ConvertTo-Json -Compress
