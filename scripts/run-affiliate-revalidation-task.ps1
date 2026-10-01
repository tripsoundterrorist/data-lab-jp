[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = "C:\github\data-lab-jp"
$PythonExecutable = "C:\Users\User\AppData\Local\Programs\Python\Python310\python.exe"
$RunnerPath = Join-Path $RepoRoot "scripts\affiliate_local_lifecycle_revalidation.py"
$HealthPath = Join-Path $RepoRoot "scripts\affiliate_public_route_health.py"
$NotificationDryRunPath = Join-Path $RepoRoot "scripts\affiliate_route_failure_notification_dry_run.py"
$NotificationLivePath = Join-Path $RepoRoot "scripts\affiliate_route_failure_notification_live.py"
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
if (-not (Test-Path -LiteralPath $HealthPath -PathType Leaf)) {
    [Console]::Error.WriteLine("wrapper_error=HEALTH_CHECK_MISSING")
    exit 24
}
if (-not (Test-Path -LiteralPath $NotificationDryRunPath -PathType Leaf)) {
    [Console]::Error.WriteLine("wrapper_error=NOTIFICATION_DRY_RUN_MISSING")
    exit 25
}
if (-not (Test-Path -LiteralPath $NotificationLivePath -PathType Leaf)) {
    [Console]::Error.WriteLine("wrapper_error=NOTIFICATION_LIVE_MISSING")
    exit 26
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
$revalidationResult = & $PythonExecutable -B $RunnerPath --execute --confirm LIVE_LOCAL_DMM_D1_REVALIDATION 2>$null
$revalidationExitCode = $LASTEXITCODE
$healthResult = & $PythonExecutable -B $HealthPath 2>$null
$healthExitCode = $LASTEXITCODE

try {
    $parsedRevalidation = $revalidationResult | ConvertFrom-Json -ErrorAction Stop
    $parsedHealth = $healthResult | ConvertFrom-Json -ErrorAction Stop
    $allowedRevalidationStatus = $parsedRevalidation.status -in @("COMPLETED", "FAILED_SAFE", "BLOCKED")
    $allowedMode = $parsedRevalidation.mode -eq "LIVE"
    $allowedHealthStatus = $parsedHealth.status -in @("HEALTHY", "FAILED_SAFE")
    $healthIsReadOnly = $parsedHealth.external_write_performed -eq $false
    if (-not $allowedRevalidationStatus -or -not $allowedMode -or
        -not $allowedHealthStatus -or -not $healthIsReadOnly) {
        throw "invalid result"
    }
    $wrapperRecord = [ordered]@{
        version = "0.2"
        revalidation = $parsedRevalidation
        public_route_health = $parsedHealth
    }
    $wrapperJson = $wrapperRecord | ConvertTo-Json -Depth 5 -Compress
    $notificationDryResult = $wrapperJson |
        & $PythonExecutable -B $NotificationDryRunPath 2>$null
    $notificationDryExitCode = $LASTEXITCODE
    $parsedNotificationDry = $notificationDryResult | ConvertFrom-Json -ErrorAction Stop
    if ($parsedNotificationDry.status -notin @("SUPPRESSED_HEALTHY", "READY_NO_SEND") -or
        $parsedNotificationDry.external_send_performed -ne $false -or
        $parsedNotificationDry.delivery_attempted -ne $false) {
        throw "invalid notification dry run"
    }
    $notificationLiveResult = $wrapperJson |
        & $PythonExecutable -B $NotificationLivePath 2>$null
    $notificationLiveExitCode = $LASTEXITCODE
    $parsedNotificationLive = $notificationLiveResult | ConvertFrom-Json -ErrorAction Stop
    if ($parsedNotificationLive.status -notin @("SUPPRESSED_HEALTHY", "DELIVERED", "DUPLICATE_SUPPRESSED")) {
        throw "invalid notification live result"
    }
    $record = [ordered]@{
        version = "0.4"
        revalidation = $parsedRevalidation
        public_route_health = $parsedHealth
        failure_notification_dry_run = $parsedNotificationDry
        failure_notification_live = $parsedNotificationLive
    }
    $record | ConvertTo-Json -Depth 6 -Compress |
        Set-Content -LiteralPath $LogPath -Encoding UTF8 -NoNewline
}
catch {
    [Console]::Error.WriteLine("wrapper_error=RUNNER_RESULT_INVALID")
    exit 23
}

if ($revalidationExitCode -ne 0) { exit $revalidationExitCode }
if ($healthExitCode -ne 0) { exit 30 }
if ($notificationDryExitCode -ne 0) { exit 31 }
if ($notificationLiveExitCode -ne 0) { exit 32 }
exit 0
