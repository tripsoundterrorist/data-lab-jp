[CmdletBinding()]
param(
    [string]$RepoRoot = "C:\github\data-lab-jp",
    [string]$DatabasePath = "",
    [string]$OutputDirectory = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$PythonExecutable = "C:\Users\User\AppData\Local\Programs\Python\Python310\python.exe"
$RunnerPath = Join-Path $RepoRoot "scripts\revenue_mvp_product_refresh_candidate.py"
if (-not $DatabasePath) {
    $DatabasePath = Join-Path $RepoRoot "data\data-lab.db"
}
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $env:LOCALAPPDATA "DATA-LAB\product-refresh-candidates"
}
$RetentionDays = 7

foreach ($required in @($PythonExecutable, $RunnerPath, $DatabasePath)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        [Console]::Error.WriteLine("wrapper_error=REQUIRED_INPUT_MISSING")
        exit 20
    }
}

try {
    if (-not (Test-Path -LiteralPath $OutputDirectory -PathType Container)) {
        New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
    }
    $resolvedOutput = (Resolve-Path -LiteralPath $OutputDirectory).Path
    $resolvedRepo = (Resolve-Path -LiteralPath $RepoRoot).Path
    if ($resolvedOutput.StartsWith($resolvedRepo + "\", [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "output inside repository"
    }
    $cutoff = [DateTime]::UtcNow.AddDays(-$RetentionDays)
    Get-ChildItem -LiteralPath $OutputDirectory -File |
        Where-Object {
            $_.Name -match '^candidate-[0-9a-f]{64}\.(html|json)$' -and
            $_.LastWriteTimeUtc -lt $cutoff
        } |
        Remove-Item -Force -ErrorAction Stop
}
catch {
    [Console]::Error.WriteLine("wrapper_error=OUTPUT_INITIALIZATION_FAILED")
    exit 21
}

try {
    $databaseSha = (Get-FileHash -LiteralPath $DatabasePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($databaseSha -notmatch '^[0-9a-f]{64}$') {
        throw "invalid database hash"
    }
}
catch {
    [Console]::Error.WriteLine("wrapper_error=DATABASE_HASH_FAILED")
    exit 22
}

$evaluatedAt = [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
$candidatePath = Join-Path $OutputDirectory ("candidate-{0}.html" -f $databaseSha)
$receiptPath = Join-Path $OutputDirectory ("candidate-{0}.json" -f $databaseSha)
$result = & $PythonExecutable -B $RunnerPath `
    --db $DatabasePath `
    --expected-db-sha256 $databaseSha `
    --evaluated-at $evaluatedAt `
    --output $candidatePath `
    --expected-count 100 2>$null
$exitCode = $LASTEXITCODE

try {
    $parsed = $result | ConvertFrom-Json -ErrorAction Stop
    $safe = (
        $parsed.status -in @("OFFLINE_REFRESH_CANDIDATE_READY", "BLOCKED") -and
        $parsed.publication_allowed -eq $false -and
        $parsed.production_write_performed -eq $false -and
        $parsed.d1_write_performed -eq $false
    )
    if (-not $safe) {
        throw "unsafe result"
    }
    if ($parsed.status -eq "OFFLINE_REFRESH_CANDIDATE_READY") {
        if (-not (Test-Path -LiteralPath $candidatePath -PathType Leaf)) {
            throw "candidate missing"
        }
        $candidateSha = (Get-FileHash -LiteralPath $candidatePath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($candidateSha -ne $parsed.candidate_sha256) {
            throw "candidate hash mismatch"
        }
    }
    $result | Set-Content -LiteralPath $receiptPath -Encoding UTF8 -NoNewline
}
catch {
    if (Test-Path -LiteralPath $candidatePath -PathType Leaf) {
        Remove-Item -LiteralPath $candidatePath -Force -ErrorAction SilentlyContinue
    }
    [Console]::Error.WriteLine("wrapper_error=RUNNER_RESULT_INVALID")
    exit 23
}

exit $exitCode
