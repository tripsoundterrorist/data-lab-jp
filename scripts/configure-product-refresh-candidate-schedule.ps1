[CmdletBinding()]
param([switch]$Apply)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$TaskName = "DATA LAB Daily Product Refresh Candidate"
$WrapperPath = "C:\github\data-lab-jp\scripts\run-product-refresh-candidate-task.ps1"
$PowerShellPath = "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
$Arguments = '-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $WrapperPath + '"'
$PlannedTime = "16:35"
$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
$result = [ordered]@{
    version = "0.1"
    task_name = $TaskName
    apply_requested = [bool]$Apply
    planned_time_jst = $PlannedTime
    existing = $null -ne $existing
    action_matches = $false
    daily_trigger_matches = $false
    created = $false
    publication_allowed = $false
    production_write_performed = $false
}

if ($null -ne $existing) {
    $actions = @($existing.Actions)
    $triggers = @($existing.Triggers)
    $result.action_matches = ($actions.Count -eq 1 -and $actions[0].Execute -eq $PowerShellPath -and $actions[0].Arguments -eq $Arguments)
    $result.daily_trigger_matches = ($triggers.Count -eq 1 -and $triggers[0].DaysInterval -eq 1 -and ([datetime]$triggers[0].StartBoundary).ToString("HH:mm") -eq $PlannedTime)
    if (-not $result.action_matches -or -not $result.daily_trigger_matches) {
        $result.status = "BLOCKED_EXISTING_TASK_MISMATCH"
        $result | ConvertTo-Json -Compress
        exit 2
    }
    $result.status = "ALREADY_CONFIGURED"
    $result | ConvertTo-Json -Compress
    exit 0
}
if (-not $Apply) {
    $result.status = "READY_TO_CREATE"
    $result | ConvertTo-Json -Compress
    exit 0
}
if (-not (Test-Path -LiteralPath $WrapperPath -PathType Leaf)) {
    $result.status = "BLOCKED_WRAPPER_MISSING"
    $result | ConvertTo-Json -Compress
    exit 3
}

$action = New-ScheduledTaskAction -Execute $PowerShellPath -Argument $Arguments
$trigger = New-ScheduledTaskTrigger -Daily -At $PlannedTime
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Prepare one private offline DATA LAB product refresh candidate; never publish." | Out-Null

$created = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
$result.created = $true
$result.action_matches = (@($created.Actions).Count -eq 1 -and $created.Actions[0].Execute -eq $PowerShellPath -and $created.Actions[0].Arguments -eq $Arguments)
$result.daily_trigger_matches = (@($created.Triggers).Count -eq 1 -and $created.Triggers[0].DaysInterval -eq 1 -and ([datetime]$created.Triggers[0].StartBoundary).ToString("HH:mm") -eq $PlannedTime)
$result.status = if ($result.action_matches -and $result.daily_trigger_matches) { "CREATED" } else { "BLOCKED_POST_CREATE_VERIFICATION_FAILED" }
$result | ConvertTo-Json -Compress
if ($result.status -ne "CREATED") { exit 4 }
exit 0
