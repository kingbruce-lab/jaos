param(
    [string]$BackupRoot = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$agentRoot = Join-Path $projectRoot "agent"
$python = Join-Path $agentRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Agent virtual environment is missing."
}

if (-not $BackupRoot) {
    $BackupRoot = Join-Path $agentRoot "backups"
}

$latest = Get-ChildItem -LiteralPath $BackupRoot -Directory |
    Where-Object { $_.Name -like "jingao-*" } |
    Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 1

if (-not $latest) {
    throw "No verifiable backup was found."
}

Set-Location -LiteralPath $agentRoot
& $python -m app.cli verify-backup --path $latest.FullName --restore-check
exit $LASTEXITCODE
