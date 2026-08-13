[CmdletBinding()]
param(
    [string]$OutputDirectory
)

$ErrorActionPreference = "Stop"
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)

$projectRoot = [System.IO.Path]::GetFullPath(
    (Split-Path -Parent $PSScriptRoot)
)
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $projectRoot "outputs\nas"
}
$resolvedOutput = [System.IO.Path]::GetFullPath($OutputDirectory)
if (-not $resolvedOutput.StartsWith(
    $projectRoot,
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "Output directory must be inside the project root."
}

New-Item -ItemType Directory -Path $resolvedOutput -Force | Out-Null

$versionPath = Join-Path $projectRoot "VERSION"
if (-not (Test-Path -LiteralPath $versionPath)) {
    throw "VERSION file is required."
}
$version = (Get-Content -LiteralPath $versionPath -Raw -Encoding utf8).Trim()
if ($version -notmatch '^\d+\.\d+\.\d+$') {
    throw "VERSION must use semantic version format, for example 1.0.0."
}
$gitCommit = "uncommitted"
$gitStatus = @()
$nativeErrorPreference = $ErrorActionPreference
$ErrorActionPreference = "SilentlyContinue"
try {
    $candidateCommit = (& git -C $projectRoot rev-parse --verify HEAD 2>$null)
    if ($LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($candidateCommit)) {
        $gitCommit = $candidateCommit.Trim()
    }
    $gitStatus = (& git -C $projectRoot status --porcelain 2>$null)
} finally {
    $ErrorActionPreference = $nativeErrorPreference
}
$gitState = if ($gitStatus) { "dirty" } else { "clean" }

$packageTimestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$stagingDirectory = Join-Path $resolvedOutput ".staging-$packageTimestamp"
$archivePath = Join-Path $resolvedOutput "jaos-v$version-nas-$packageTimestamp.zip"

$resolvedStaging = [System.IO.Path]::GetFullPath($stagingDirectory)
if (-not $resolvedStaging.StartsWith(
    ($resolvedOutput + [System.IO.Path]::DirectorySeparatorChar),
    [System.StringComparison]::OrdinalIgnoreCase
)) {
    throw "Staging directory is outside the expected output directory."
}

New-Item -ItemType Directory -Path $resolvedStaging | Out-Null

try {
    $rootFiles = @(
        ".dockerignore",
        ".env.example",
        "CHANGELOG.md",
        "compose.yaml",
        "Dockerfile",
        "eslint.config.mjs",
        "next.config.ts",
        "package.json",
        "pnpm-lock.yaml",
        "pnpm-workspace.yaml",
        "postcss.config.mjs",
        "README.md",
        "tsconfig.json",
        "VERSION",
        "vite.config.ts"
    )
    foreach ($relativeFile in $rootFiles) {
        $sourceFile = Join-Path $projectRoot $relativeFile
        if (Test-Path -LiteralPath $sourceFile) {
            Copy-Item -LiteralPath $sourceFile -Destination $resolvedStaging
        }
    }

    $directoryCopies = @(
        @{ Source = "app"; Destination = "app" },
        @{ Source = "public"; Destination = "public" },
        @{ Source = "worker"; Destination = "worker" },
        @{ Source = "drizzle"; Destination = "drizzle" },
        @{ Source = "agent\app"; Destination = "agent\app" },
        @{ Source = "agent\assets"; Destination = "agent\assets" }
    )
    foreach ($copyItem in $directoryCopies) {
        $sourceDirectory = Join-Path $projectRoot $copyItem.Source
        if (-not (Test-Path -LiteralPath $sourceDirectory)) {
            continue
        }
        $destinationDirectory = Join-Path $resolvedStaging $copyItem.Destination
        $destinationParent = Split-Path -Parent $destinationDirectory
        New-Item -ItemType Directory -Path $destinationParent -Force | Out-Null
        Copy-Item `
            -LiteralPath $sourceDirectory `
            -Destination $destinationDirectory `
            -Recurse
    }

    $singleFileCopies = @(
        @{ Source = "agent\.dockerignore"; Destination = "agent\.dockerignore" },
        @{ Source = "agent\Dockerfile"; Destination = "agent\Dockerfile" },
        @{ Source = "agent\requirements.txt"; Destination = "agent\requirements.txt" },
        @{ Source = "build\sites-vite-plugin.ts"; Destination = "build\sites-vite-plugin.ts" },
        @{ Source = "docs\发布与回滚.md"; Destination = "docs\release-and-rollback.md" },
        @{ Source = "scripts\configure-fnos-docker-mirror.sh"; Destination = "scripts\configure-fnos-docker-mirror.sh" },
        @{ Source = "scripts\deploy-nas-runtime.sh"; Destination = "scripts\deploy-nas-runtime.sh" },
        @{ Source = "scripts\manage-nas-runtime.sh"; Destination = "scripts\manage-nas-runtime.sh" },
        @{ Source = "scripts\nas-preflight.sh"; Destination = "scripts\nas-preflight.sh" },
        @{ Source = "scripts\install-offsite-backup-timer.sh"; Destination = "scripts\install-offsite-backup-timer.sh" },
        @{ Source = "scripts\sync-offsite-backup.sh"; Destination = "scripts\sync-offsite-backup.sh" },
        @{ Source = "scripts\start-web.mjs"; Destination = "scripts\start-web.mjs" },
        @{ Source = "scripts\web-security.mjs"; Destination = "scripts\web-security.mjs" },
        @{ Source = "scripts\verify-nas-runtime.sh"; Destination = "scripts\verify-nas-runtime.sh" }
    )
    foreach ($copyItem in $singleFileCopies) {
        $sourceFile = Join-Path $projectRoot $copyItem.Source
        if (-not (Test-Path -LiteralPath $sourceFile)) {
            continue
        }
        $destinationFile = Join-Path $resolvedStaging $copyItem.Destination
        $destinationParent = Split-Path -Parent $destinationFile
        New-Item -ItemType Directory -Path $destinationParent -Force | Out-Null
        Copy-Item -LiteralPath $sourceFile -Destination $destinationFile
    }

    $manifest = @(
        "JAOS NAS deployment package"
        "Version: $version"
        "Git commit: $gitCommit"
        "Git state: $gitState"
        "Generated: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
        "Target: fnOS / Docker Compose production"
        "Security: no .env, password, API key, database, or knowledge source is included."
        "Integrity: verify SHA256SUMS before deployment."
        "Deployment and rollback: docs/release-and-rollback.md"
    )
    $manifestPath = Join-Path $resolvedStaging "DEPLOYMENT-PACKAGE.txt"
    [System.IO.File]::WriteAllText(
        $manifestPath,
        (($manifest -join "`n") + "`n"),
        $utf8NoBom
    )

    Get-ChildItem `
        -LiteralPath $resolvedStaging `
        -Directory `
        -Recurse `
        -Filter "__pycache__" |
        ForEach-Object {
            $checkedCache = [System.IO.Path]::GetFullPath($_.FullName)
            if ($checkedCache.StartsWith(
                ($resolvedStaging + [System.IO.Path]::DirectorySeparatorChar),
                [System.StringComparison]::OrdinalIgnoreCase
            )) {
                Remove-Item -LiteralPath $checkedCache -Recurse -Force
            }
        }
    Get-ChildItem `
        -LiteralPath $resolvedStaging `
        -File `
        -Recurse `
        -Filter "*.pyc" |
        Remove-Item -Force

    $checksumLines = Get-ChildItem -LiteralPath $resolvedStaging -File -Recurse |
        Sort-Object FullName |
        ForEach-Object {
            $relativeEntry = $_.FullName.Substring(
                $resolvedStaging.Length + 1
            ).Replace(
                [System.IO.Path]::DirectorySeparatorChar,
                [char]"/"
            )
            $fileHash = Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
            "$($fileHash.Hash.ToLowerInvariant())  $relativeEntry"
        }
    [System.IO.File]::WriteAllText(
        (Join-Path $resolvedStaging "SHA256SUMS"),
        (($checksumLines -join "`n") + "`n"),
        $utf8NoBom
    )

    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archiveStream = [System.IO.File]::Open(
        $archivePath,
        [System.IO.FileMode]::CreateNew
    )
    $zipArchive = New-Object System.IO.Compression.ZipArchive(
        $archiveStream,
        [System.IO.Compression.ZipArchiveMode]::Create,
        $false
    )
    try {
        Get-ChildItem -LiteralPath $resolvedStaging -File -Recurse |
            Sort-Object FullName |
            ForEach-Object {
                $relativeEntry = $_.FullName.Substring(
                    $resolvedStaging.Length + 1
                ).Replace(
                    [System.IO.Path]::DirectorySeparatorChar,
                    [char]"/"
                )
                [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
                    $zipArchive,
                    $_.FullName,
                    $relativeEntry,
                    [System.IO.Compression.CompressionLevel]::Optimal
                ) | Out-Null
            }
    } finally {
        $zipArchive.Dispose()
        $archiveStream.Dispose()
    }
} finally {
    if (Test-Path -LiteralPath $resolvedStaging) {
        $checkedStaging = [System.IO.Path]::GetFullPath($resolvedStaging)
        if ($checkedStaging.StartsWith(
            ($resolvedOutput + [System.IO.Path]::DirectorySeparatorChar),
            [System.StringComparison]::OrdinalIgnoreCase
        )) {
            Remove-Item -LiteralPath $checkedStaging -Recurse -Force
        }
    }
}

$archiveHash = Get-FileHash -LiteralPath $archivePath -Algorithm SHA256
Write-Output "PACKAGE=$archivePath"
Write-Output "SHA256=$($archiveHash.Hash)"
Write-Output "VERSION=$version"
Write-Output "GIT_COMMIT=$gitCommit"
Write-Output "GIT_STATE=$gitState"
