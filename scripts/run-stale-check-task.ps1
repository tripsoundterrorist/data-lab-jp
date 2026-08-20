[CmdletBinding()]
param(
    [string]$OlderThanMinutes = "60",
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = "C:\github\data-lab-jp"
$PythonExecutable = "C:\Users\User\AppData\Local\Programs\Python\Python310\python.exe"
$CheckerPath = Join-Path $RepoRoot "scripts\check-stale-collection-runs.py"
$SourceDatabasePath = Join-Path $RepoRoot "data\data-lab.db"
$LogDirectory = Join-Path $RepoRoot "logs\stale-check"

$DefaultOlderThanMinutes = 60
$MinimumOlderThanMinutes = 30
$MaximumOlderThanMinutes = 1440
$LogRetentionDays = 30

$ExitPythonMissing = 20
$ExitPathMissing = 21
$ExitLogInitializationFailure = 22
$ExitInvalidArgument = 23
$ExitSourceDatabaseMissing = 24
$ExitCheckerLaunchFailure = 25

function Write-SafeConsoleError {
    param([string]$Code)
    [Console]::Error.WriteLine("Stale-check wrapper error: {0}" -f $Code)
}

function ConvertTo-BoundedMinutes {
    param([string]$Value)

    $parsed = 0
    if (-not [int]::TryParse($Value, [ref]$parsed)) {
        return $null
    }
    if ($parsed -lt $MinimumOlderThanMinutes -or $parsed -gt $MaximumOlderThanMinutes) {
        return $null
    }
    return $parsed
}

$ParsedOlderThanMinutes = ConvertTo-BoundedMinutes -Value $OlderThanMinutes
if ($null -eq $ParsedOlderThanMinutes) {
    Write-SafeConsoleError -Code "INVALID_OLDER_THAN_MINUTES"
    exit $ExitInvalidArgument
}

if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) {
    Write-SafeConsoleError -Code "PYTHON_EXECUTABLE_MISSING"
    exit $ExitPythonMissing
}
if (-not (Test-Path -LiteralPath $RepoRoot -PathType Container)) {
    Write-SafeConsoleError -Code "REPO_ROOT_MISSING"
    exit $ExitPathMissing
}
if (-not (Test-Path -LiteralPath $CheckerPath -PathType Leaf)) {
    Write-SafeConsoleError -Code "STALE_CHECKER_MISSING"
    exit $ExitPathMissing
}
if (-not (Test-Path -LiteralPath $SourceDatabasePath -PathType Leaf)) {
    Write-SafeConsoleError -Code "SOURCE_DATABASE_MISSING"
    exit $ExitSourceDatabaseMissing
}

try {
    if (-not (Test-Path -LiteralPath $LogDirectory -PathType Container)) {
        New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
    }
    $timestamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
    $LogPath = Join-Path $LogDirectory ("stale-check-{0}-{1}.log" -f $timestamp, $PID)
    New-Item -ItemType File -Path $LogPath -ErrorAction Stop | Out-Null
}
catch {
    Write-SafeConsoleError -Code "LOG_INITIALIZATION_FAILURE"
    exit $ExitLogInitializationFailure
}

function Write-SafeLog {
    param([string]$Message)
    $Message | Tee-Object -FilePath $LogPath -Append
}

$wrapperStarted = [DateTime]::UtcNow
Write-SafeLog ("wrapper_started_at={0}" -f $wrapperStarted.ToString("o"))
Write-SafeLog ("mode={0}" -f $(if ($DryRun) { "dry_run" } else { "check" }))
Write-SafeLog ("older_than_minutes={0}" -f $ParsedOlderThanMinutes)

if (-not $DryRun) {
    try {
        $cutoff = [DateTime]::UtcNow.AddDays(-$LogRetentionDays)
        Get-ChildItem -LiteralPath $LogDirectory -File -Filter "stale-check-*.log" |
            Where-Object { $_.FullName -ne $LogPath -and $_.LastWriteTimeUtc -lt $cutoff } |
            Remove-Item -Force -ErrorAction Stop
    }
    catch {
        Write-SafeLog "warning=LOG_ROTATION_FAILED"
    }
}

$checkerArguments = @(
    $CheckerPath,
    "--db", $SourceDatabasePath,
    "--older-than-minutes", $ParsedOlderThanMinutes.ToString()
)

Write-SafeLog "checker_started=true"
Push-Location -LiteralPath $RepoRoot
try {
    & $PythonExecutable @checkerArguments 2>&1 |
        Tee-Object -FilePath $LogPath -Append
    $checkerExitCode = $LASTEXITCODE
}
catch {
    $checkerExitCode = $ExitCheckerLaunchFailure
    Write-SafeLog "wrapper_error=CHECKER_LAUNCH_FAILURE"
}
finally {
    Pop-Location
}

Write-SafeLog ("checker_exit_code={0}" -f $checkerExitCode)
$wrapperFinished = [DateTime]::UtcNow
$elapsed = ($wrapperFinished - $wrapperStarted).TotalSeconds
Write-SafeLog ("wrapper_finished_at={0}" -f $wrapperFinished.ToString("o"))
Write-SafeLog ("elapsed_seconds={0:F3}" -f $elapsed)
Write-SafeLog ("wrapper_exit_code={0}" -f $checkerExitCode)

exit $checkerExitCode
