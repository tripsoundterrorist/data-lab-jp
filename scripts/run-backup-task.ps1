[CmdletBinding()]
param(
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = "C:\github\data-lab-jp"
$PythonExecutable = "C:\Users\User\AppData\Local\Programs\Python\Python310\python.exe"
$BackupScriptPath = Join-Path $RepoRoot "scripts\backup-data-lab-db.py"
$SourceDatabasePath = Join-Path $RepoRoot "data\data-lab.db"
$LogDirectory = Join-Path $RepoRoot "logs\backup"
$LogRetentionDays = 30

$ExitPythonMissing = 20
$ExitPathMissing = 21
$ExitLogInitializationFailure = 22
$ExitSourceDatabaseMissing = 24
$ExitScriptLaunchFailure = 25

function Write-SafeConsoleError {
    param([string]$Code)
    [Console]::Error.WriteLine("Backup wrapper error: {0}" -f $Code)
}

if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) {
    Write-SafeConsoleError -Code "PYTHON_EXECUTABLE_MISSING"
    exit $ExitPythonMissing
}
if (-not (Test-Path -LiteralPath $RepoRoot -PathType Container)) {
    Write-SafeConsoleError -Code "REPO_ROOT_MISSING"
    exit $ExitPathMissing
}
if (-not (Test-Path -LiteralPath $BackupScriptPath -PathType Leaf)) {
    Write-SafeConsoleError -Code "BACKUP_SCRIPT_MISSING"
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
    $LogPath = Join-Path $LogDirectory ("backup-{0}-{1}.log" -f $timestamp, $PID)
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
Write-SafeLog ("mode={0}" -f $(if ($DryRun) { "dry_run" } else { "backup" }))

if (-not $DryRun) {
    try {
        $cutoff = [DateTime]::UtcNow.AddDays(-$LogRetentionDays)
        Get-ChildItem -LiteralPath $LogDirectory -File -Filter "backup-*.log" |
            Where-Object { $_.FullName -ne $LogPath -and $_.LastWriteTimeUtc -lt $cutoff } |
            Remove-Item -Force -ErrorAction Stop
    }
    catch {
        Write-SafeLog "warning=LOG_ROTATION_FAILED"
    }
}

$backupArguments = @($BackupScriptPath)
if ($DryRun) {
    $backupArguments += "--dry-run"
}

Write-SafeLog "backup_script_started=true"
Push-Location -LiteralPath $RepoRoot
try {
    & $PythonExecutable @backupArguments 2>&1 |
        Tee-Object -FilePath $LogPath -Append
    $backupScriptExitCode = $LASTEXITCODE
}
catch {
    $backupScriptExitCode = $ExitScriptLaunchFailure
    Write-SafeLog "wrapper_error=BACKUP_SCRIPT_LAUNCH_FAILURE"
}
finally {
    Pop-Location
}

Write-SafeLog ("backup_script_exit_code={0}" -f $backupScriptExitCode)
$wrapperFinished = [DateTime]::UtcNow
$elapsed = ($wrapperFinished - $wrapperStarted).TotalSeconds
Write-SafeLog ("wrapper_finished_at={0}" -f $wrapperFinished.ToString("o"))
Write-SafeLog ("elapsed_seconds={0:F3}" -f $elapsed)
Write-SafeLog ("wrapper_exit_code={0}" -f $backupScriptExitCode)

exit $backupScriptExitCode
