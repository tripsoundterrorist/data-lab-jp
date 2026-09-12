[CmdletBinding()]
param(
    [ValidateRange(1, 100)][int]$Hits = 50,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = "C:\github\data-lab-jp"
$PythonExecutable = "C:\Users\User\AppData\Local\Programs\Python\Python310\python.exe"
$CollectorPath = Join-Path $RepoRoot "scripts\collect-category-items.py"
$HealthCheckPath = Join-Path $RepoRoot "scripts\category_collection_health.py"
$LogDirectory = Join-Path $RepoRoot "logs\category-collector"
$arguments = @($CollectorPath, "--hits", $Hits.ToString())
if ($DryRun) { $arguments += "--dry-run" }

if (-not (Test-Path -LiteralPath $PythonExecutable -PathType Leaf)) { throw "PYTHON_EXECUTABLE_MISSING" }
if (-not (Test-Path -LiteralPath $CollectorPath -PathType Leaf)) { throw "COLLECTOR_MISSING" }
if (-not $DryRun -and -not (Test-Path -LiteralPath $HealthCheckPath -PathType Leaf)) { throw "HEALTH_CHECK_MISSING" }
if (-not $DryRun -and -not (Test-Path -LiteralPath (Join-Path $RepoRoot ".env") -PathType Leaf)) { throw "ENV_FILE_MISSING" }

New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
$stamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$LogPath = Join-Path $LogDirectory ("category-collector-{0}-{1}.log" -f $stamp, $PID)

Push-Location -LiteralPath $RepoRoot
try {
    & $PythonExecutable @arguments 2>&1 | Tee-Object -FilePath $LogPath
    $code = $LASTEXITCODE
    if (-not $DryRun -and $code -eq 0) {
        & $PythonExecutable -B $HealthCheckPath 2>&1 | Tee-Object -FilePath $LogPath -Append
        $healthCode = $LASTEXITCODE
        if ($healthCode -ne 0) { $code = $healthCode }
    }
}
finally {
    Pop-Location
}
exit $code
