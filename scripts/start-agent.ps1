$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$agentRoot = Join-Path $projectRoot "agent"
$python = Join-Path $agentRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Agent virtual environment is missing. Install requirements.txt first."
}

Set-Location -LiteralPath $agentRoot
& $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
