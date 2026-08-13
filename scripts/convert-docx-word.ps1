param(
    [Parameter(Mandatory = $true)]
    [string]$SourcePath,
    [Parameter(Mandatory = $true)]
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"
$sourceFile = (Resolve-Path -LiteralPath $SourcePath).Path
$outputFile = [System.IO.Path]::GetFullPath($OutputPath)
$outputDirectory = [System.IO.Path]::GetDirectoryName($outputFile)

if (-not (Test-Path -LiteralPath $outputDirectory)) {
    New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null
}

$wordApplication = $null
$wordDocument = $null
try {
    $wordApplication = New-Object -ComObject Word.Application
    $wordApplication.Visible = $false
    $wordApplication.DisplayAlerts = 0
    $wordDocument = $wordApplication.Documents.Open(
        $sourceFile,
        $false,
        $true,
        $false
    )
    $wordDocument.ExportAsFixedFormat($outputFile, 17)
}
finally {
    if ($wordDocument) {
        $wordDocument.Close($false)
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($wordDocument)
    }
    if ($wordApplication) {
        $wordApplication.Quit()
        [void][System.Runtime.InteropServices.Marshal]::ReleaseComObject($wordApplication)
    }
    [GC]::Collect()
    [GC]::WaitForPendingFinalizers()
}
