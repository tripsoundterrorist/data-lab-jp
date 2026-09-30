[CmdletBinding()]
param(
    [string]$RepoRoot = "C:\github\data-lab-jp",
    [string]$DatabasePath = "",
    [string]$LogDirectory = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$PythonExecutable = "C:\Users\User\AppData\Local\Programs\Python\Python310\python.exe"
$RunnerPath = Join-Path $RepoRoot "scripts\revenue_mvp_product_refresh_rehearsal.py"
$SourcePath = Join-Path $RepoRoot "items\index.html"
if (-not $DatabasePath) {
    $DatabasePath = Join-Path $RepoRoot "data\data-lab.db"
}
if (-not $LogDirectory) {
    $LogDirectory = Join-Path $RepoRoot "logs\product-refresh-assessment"
}
$RetentionDays = 30

foreach ($required in @($PythonExecutable, $RunnerPath, $SourcePath, $DatabasePath)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        [Console]::Error.WriteLine("wrapper_error=REQUIRED_INPUT_MISSING")
        exit 20
    }
}

try {
    if (-not (Test-Path -LiteralPath $LogDirectory -PathType Container)) {
        New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
    }
    $cutoff = [DateTime]::UtcNow.AddDays(-$RetentionDays)
    Get-ChildItem -LiteralPath $LogDirectory -File -Filter "assessment-*.json" |
        Where-Object { $_.LastWriteTimeUtc -lt $cutoff } |
        Remove-Item -Force -ErrorAction Stop
}
catch {
    [Console]::Error.WriteLine("wrapper_error=LOG_INITIALIZATION_FAILED")
    exit 21
}

$timestamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$LogPath = Join-Path $LogDirectory ("assessment-{0}-{1}.json" -f $timestamp, $PID)
$result = & $PythonExecutable -B $RunnerPath `
    --source $SourcePath `
    --db $DatabasePath `
    --expected-count 100 2>$null
$exitCode = $LASTEXITCODE

try {
    $parsed = $result | ConvertFrom-Json -ErrorAction Stop
    $allowedStatus = $parsed.status -in @("READY_FOR_SEPARATE_REFRESH_CANDIDATE", "BLOCKED")
    $safeBoundary = (
        $parsed.publication_allowed -eq $false -and
        $parsed.production_write_performed -eq $false
    )
    if (-not $allowedStatus -or -not $safeBoundary) {
        throw "invalid result"
    }
}
catch {
    [Console]::Error.WriteLine("wrapper_error=RUNNER_RESULT_INVALID")
    exit 22
}

try {
    $result | Set-Content -LiteralPath $LogPath -Encoding UTF8 -NoNewline
}
catch {
    [Console]::Error.WriteLine("wrapper_error=LOG_WRITE_FAILED")
    exit 23
}

exit $exitCode
