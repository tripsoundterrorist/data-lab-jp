[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = "C:\github\data-lab-jp"
$PythonExecutable = "C:\Users\User\AppData\Local\Programs\Python\Python310\python.exe"
$RunnerPath = Join-Path $RepoRoot "scripts\affiliate_local_lifecycle_revalidation.py"
$LogDirectory = Join-Path $RepoRoot "logs\affiliate-revalidation"
$RetentionDays = 30

if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) {
    [Console]::Error.WriteLine("wrapper_error=PYTHON_EXECUTABLE_MISSING")
    exit 20
}
if (-not (Test-Path -LiteralPath $RunnerPath -PathType Leaf)) {
    [Console]::Error.WriteLine("wrapper_error=RUNNER_MISSING")
    exit 21
}

try {
    if (-not (Test-Path -LiteralPath $LogDirectory -PathType Container)) {
        New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
    }
    $cutoff = [DateTime]::UtcNow.AddDays(-$RetentionDays)
    Get-ChildItem -LiteralPath $LogDirectory -File -Filter "revalidation-*.json" |
        Where-Object { $_.LastWriteTimeUtc -lt $cutoff } |
        Remove-Item -Force -ErrorAction Stop
}
catch {
    [Console]::Error.WriteLine("wrapper_error=LOG_INITIALIZATION_FAILED")
    exit 22
}

$timestamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$LogPath = Join-Path $LogDirectory ("revalidation-{0}-{1}.json" -f $timestamp, $PID)
$result = & $PythonExecutable -B $RunnerPath --execute --confirm LIVE_LOCAL_DMM_D1_REVALIDATION 2>$null
$exitCode = $LASTEXITCODE

try {
    $parsed = $result | ConvertFrom-Json -ErrorAction Stop
    $allowedStatus = $parsed.status -in @("COMPLETED", "FAILED_SAFE", "BLOCKED")
    $allowedMode = $parsed.mode -eq "LIVE"
    if (-not $allowedStatus -or -not $allowedMode) {
        throw "invalid result"
    }
    $result | Set-Content -LiteralPath $LogPath -Encoding UTF8 -NoNewline
}
catch {
    [Console]::Error.WriteLine("wrapper_error=RUNNER_RESULT_INVALID")
    exit 23
}

exit $exitCode
