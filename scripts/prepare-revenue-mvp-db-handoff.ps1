[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$DatabasePath,

    [string]$PythonExecutable = "python"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Version = "0.1"
$AuditScript = Join-Path $PSScriptRoot "revenue_mvp_db_audit.py"

function Write-SafeResult {
    param(
        [string]$Status,
        [bool]$IdentityStable,
        [AllowNull()][string]$ExpectedSha256,
        [AllowNull()][object]$Audit,
        [string[]]$ReasonCodes
    )

    $result = [ordered]@{
        version = $Version
        status = $Status
        read_only = $true
        identity_stable = $IdentityStable
        expected_sha256 = $ExpectedSha256
        database_size_bytes = if ($null -eq $Audit) { $null } else { $Audit.database_size_bytes }
        items_count = if ($null -eq $Audit) { $null } else { $Audit.items_count }
        item_snapshots_count = if ($null -eq $Audit) { $null } else { $Audit.item_snapshots_count }
        collection_runs_count = if ($null -eq $Audit) { $null } else { $Audit.collection_runs_count }
        oldest_observed_at = if ($null -eq $Audit) { $null } else { $Audit.oldest_observed_at }
        latest_observed_at = if ($null -eq $Audit) { $null } else { $Audit.latest_observed_at }
        average_observations_per_item = if ($null -eq $Audit) { $null } else { $Audit.average_observations_per_item }
        integrity_check = if ($null -eq $Audit) { "unavailable" } else { $Audit.integrity_check }
        foreign_key_violation_count = if ($null -eq $Audit) { $null } else { $Audit.foreign_key_violation_count }
        upload_performed = $false
        copy_performed = $false
        reason_codes = @($ReasonCodes)
    }
    $result | ConvertTo-Json -Compress
}

try {
    if (-not (Test-Path -LiteralPath $AuditScript -PathType Leaf)) {
        throw "AUDIT_SCRIPT_UNAVAILABLE"
    }
    if (-not (Test-Path -LiteralPath $DatabasePath -PathType Leaf)) {
        Write-SafeResult -Status "BLOCKED" -IdentityStable $false `
            -ExpectedSha256 $null -Audit $null -ReasonCodes @("DATABASE_MISSING")
        exit 2
    }

    $database = Get-Item -LiteralPath $DatabasePath -Force
    if (($database.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        Write-SafeResult -Status "BLOCKED" -IdentityStable $false `
            -ExpectedSha256 $null -Audit $null -ReasonCodes @("UNSAFE_DATABASE_ENTRY")
        exit 2
    }

    $resolvedDatabase = $database.FullName
    $before = (Get-FileHash -LiteralPath $resolvedDatabase -Algorithm SHA256).Hash.ToLowerInvariant()
    $auditJson = & $PythonExecutable $AuditScript --db $resolvedDatabase 2>$null
    $auditExitCode = $LASTEXITCODE
    if ([string]::IsNullOrWhiteSpace("$auditJson")) {
        throw "AUDIT_OUTPUT_UNAVAILABLE"
    }
    $audit = $auditJson | ConvertFrom-Json
    $after = (Get-FileHash -LiteralPath $resolvedDatabase -Algorithm SHA256).Hash.ToLowerInvariant()

    if ($before -ne $after) {
        Write-SafeResult -Status "BLOCKED" -IdentityStable $false `
            -ExpectedSha256 $null -Audit $audit `
            -ReasonCodes @("DATABASE_CHANGED_DURING_HANDOFF_PREPARATION")
        exit 2
    }
    if ($auditExitCode -ne 0 -or $audit.status -ne "READY" -or -not $audit.read_only) {
        Write-SafeResult -Status "BLOCKED" -IdentityStable $true `
            -ExpectedSha256 $before -Audit $audit -ReasonCodes @($audit.reason_codes)
        exit 2
    }

    Write-SafeResult -Status "HANDOFF_READY" -IdentityStable $true `
        -ExpectedSha256 $before -Audit $audit -ReasonCodes @("DB_HANDOFF_PACKAGE_READY")
    exit 0
}
catch {
    Write-SafeResult -Status "FAIL_CLOSED" -IdentityStable $false `
        -ExpectedSha256 $null -Audit $null -ReasonCodes @("HANDOFF_PREPARATION_ERROR")
    exit 2
}
