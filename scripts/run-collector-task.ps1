[CmdletBinding()]
param(
    [string]$MaxItems = "100",
    [string]$MaxPages = "2",
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = "C:\github\data-lab-jp"
$PythonExecutable = "C:\Users\User\AppData\Local\Programs\Python\Python310\python.exe"
$CollectorPath = Join-Path $RepoRoot "scripts\collect-dmm-items.py"
$EnvPath = Join-Path $RepoRoot ".env"
$DatabasePath = Join-Path $RepoRoot "data\data-lab.db"
$LogDirectory = Join-Path $RepoRoot "logs\collector"

$DefaultMaxItems = 100
$DefaultMaxPages = 2
$MaxAllowedItems = 5000
$MaxAllowedPages = 100
$LogRetentionDays = 30

$ExitPythonMissing = 20
$ExitPathMissing = 21
$ExitLogInitializationFailure = 22
$ExitInvalidArgument = 23
$ExitRequiredFileMissing = 24

function Write-SafeConsoleError {
    param([string]$Code)
    [Console]::Error.WriteLine("Wrapper error: {0}" -f $Code)
}

function ConvertTo-BoundedInteger {
    param(
        [string]$Value,
        [int]$Minimum,
        [int]$Maximum
    )

    $parsed = 0
    if (-not [int]::TryParse($Value, [ref]$parsed)) {
        return $null
    }
    if ($parsed -lt $Minimum -or $parsed -gt $Maximum) {
        return $null
    }
    return $parsed
}

$ParsedMaxItems = ConvertTo-BoundedInteger -Value $MaxItems -Minimum 1 -Maximum $MaxAllowedItems
$ParsedMaxPages = ConvertTo-BoundedInteger -Value $MaxPages -Minimum 1 -Maximum $MaxAllowedPages

if ($null -eq $ParsedMaxItems -or $null -eq $ParsedMaxPages) {
    Write-SafeConsoleError -Code "INVALID_RUNTIME_LIMIT"
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
if (-not (Test-Path -LiteralPath $CollectorPath -PathType Leaf)) {
    Write-SafeConsoleError -Code "COLLECTOR_MISSING"
    exit $ExitPathMissing
}
if (-not (Test-Path -LiteralPath $EnvPath -PathType Leaf)) {
    Write-SafeConsoleError -Code "ENV_FILE_MISSING"
    exit $ExitRequiredFileMissing
}
if (-not (Test-Path -LiteralPath $DatabasePath -PathType Leaf)) {
    Write-SafeConsoleError -Code "DATABASE_MISSING"
    exit $ExitRequiredFileMissing
}

try {
    if (-not (Test-Path -LiteralPath $LogDirectory -PathType Container)) {
        New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
    }
    $timestamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
    $LogPath = Join-Path $LogDirectory ("collector-{0}-{1}.log" -f $timestamp, $PID)
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
Write-SafeLog ("mode={0}" -f $(if ($DryRun) { "dry_run" } else { "collector" }))
Write-SafeLog ("runtime_limits max_items={0} max_pages={1}" -f $ParsedMaxItems, $ParsedMaxPages)

if ($DryRun) {
    Write-SafeLog "prechecks=passed"
    Write-SafeLog "collector_started=false"
    Write-SafeLog "api_calls=0"
    Write-SafeLog "database_changes=0"
    Write-SafeLog "collector_exit_code=not_run"
    $wrapperFinished = [DateTime]::UtcNow
    $elapsed = ($wrapperFinished - $wrapperStarted).TotalSeconds
    Write-SafeLog ("wrapper_finished_at={0}" -f $wrapperFinished.ToString("o"))
    Write-SafeLog ("elapsed_seconds={0:F3}" -f $elapsed)
    exit 0
}

try {
    $cutoff = [DateTime]::UtcNow.AddDays(-$LogRetentionDays)
    Get-ChildItem -LiteralPath $LogDirectory -File -Filter "collector-*.log" |
        Where-Object { $_.FullName -ne $LogPath -and $_.LastWriteTimeUtc -lt $cutoff } |
        Remove-Item -Force -ErrorAction Stop
}
catch {
    Write-SafeLog "warning=LOG_ROTATION_FAILED"
}

$collectorArguments = @(
    $CollectorPath,
    "--max-items", $ParsedMaxItems.ToString(),
    "--max-pages", $ParsedMaxPages.ToString()
)

Write-SafeLog "collector_started=true"
Push-Location -LiteralPath $RepoRoot
try {
    & $PythonExecutable @collectorArguments 2>&1 |
        Tee-Object -FilePath $LogPath -Append
    $collectorExitCode = $LASTEXITCODE
}
catch {
    $collectorExitCode = 1
    Write-SafeLog "wrapper_error=COLLECTOR_LAUNCH_FAILURE"
}
finally {
    Pop-Location
}

Write-SafeLog ("collector_exit_code={0}" -f $collectorExitCode)
$wrapperFinished = [DateTime]::UtcNow
$elapsed = ($wrapperFinished - $wrapperStarted).TotalSeconds
Write-SafeLog ("wrapper_finished_at={0}" -f $wrapperFinished.ToString("o"))
Write-SafeLog ("elapsed_seconds={0:F3}" -f $elapsed)

exit $collectorExitCode
