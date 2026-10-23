# Re-enable repository-local conventions after cloning this repository.
$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath (Join-Path $repositoryRoot '.git'))) { throw 'Initialize or clone the repository first.' }
$settings = @{
    'core.hooksPath' = '.githooks'
    'commit.template' = '.gitmessage'
    'core.autocrlf' = 'false'
    'core.quotepath' = 'false'
    'pull.ff' = 'only'
    'push.default' = 'simple'
}
foreach ($item in $settings.GetEnumerator()) {
    & git -C $repositoryRoot config --local $item.Key $item.Value
    if ($LASTEXITCODE -ne 0) { throw ('Could not configure ' + $item.Key) }
}
Write-Output 'CoverWorkbench Git conventions configured for this clone.'
