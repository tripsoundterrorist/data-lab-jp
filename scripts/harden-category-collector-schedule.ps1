[CmdletBinding()]
param([switch]$Apply)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$TaskName = "DATA LAB Daily Category Collector"
$ExpectedWrapper = "C:\github\data-lab-jp\scripts\run-category-collector-task.ps1"
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
$action = @($task.Actions)
if ($action.Count -ne 1 -or $action[0].Arguments -notlike "*$ExpectedWrapper*") {
    throw "CATEGORY_COLLECTOR_TASK_ACTION_MISMATCH"
}

$before = [ordered]@{
    start_when_available = [bool]$task.Settings.StartWhenAvailable
    wake_to_run = [bool]$task.Settings.WakeToRun
    stop_if_going_on_batteries = [bool]$task.Settings.StopIfGoingOnBatteries
}
if ($Apply) {
    $task.Settings.StartWhenAvailable = $true
    $task.Settings.WakeToRun = $true
    $task.Settings.StopIfGoingOnBatteries = $false
    Set-ScheduledTask -InputObject $task | Out-Null
}

$current = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
$result = [ordered]@{
    version = "0.1"
    task_name = $TaskName
    apply_requested = [bool]$Apply
    before = $before
    current = [ordered]@{
        start_when_available = [bool]$current.Settings.StartWhenAvailable
        wake_to_run = [bool]$current.Settings.WakeToRun
        stop_if_going_on_batteries = [bool]$current.Settings.StopIfGoingOnBatteries
    }
    action_unchanged = $true
    trigger_unchanged = $true
}
$result | ConvertTo-Json -Depth 3 -Compress
if ($Apply -and (-not $current.Settings.StartWhenAvailable -or -not $current.Settings.WakeToRun -or $current.Settings.StopIfGoingOnBatteries)) {
    exit 2
}
exit 0
