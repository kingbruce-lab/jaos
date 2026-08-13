$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$bundledRoot = "C:\Users\86185\.cache\codex-runtimes\codex-primary-runtime\dependencies"
$bundledNode = Join-Path $bundledRoot "node\bin"
$bundledBin = Join-Path $bundledRoot "bin\fallback"

if (Test-Path -LiteralPath (Join-Path $bundledNode "node.exe")) {
    $env:PATH = "$bundledNode;$bundledBin;$env:PATH"
}

$pnpm = Get-Command pnpm -ErrorAction SilentlyContinue
if (-not $pnpm) {
    throw "pnpm was not found. Install Node.js 22+ and pnpm first."
}

Set-Location -LiteralPath $projectRoot
pnpm dev
