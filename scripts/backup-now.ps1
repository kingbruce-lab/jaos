param(
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$agentRoot = Join-Path $projectRoot "agent"
$python = Join-Path $agentRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Agent virtual environment is missing."
}

if (-not $OutputPath) {
    $OutputPath = Join-Path $agentRoot "backups"
}

Set-Location -LiteralPath $agentRoot
& $python -m app.cli backup --output $OutputPath
exit $LASTEXITCODE
