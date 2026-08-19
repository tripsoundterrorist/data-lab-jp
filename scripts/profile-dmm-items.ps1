[CmdletBinding()]
param(
  [ValidateSet('date', 'rank')]
  [string]$Sort = 'date'
)

$ErrorActionPreference = 'Stop'
$timeoutSeconds = 15
$envPath = Join-Path (Split-Path -Parent $PSScriptRoot) '.env'

function Get-DotEnvValue {
  param([Parameter(Mandatory)][string]$Name)

  $prefix = "$Name="
  $line = Get-Content -LiteralPath $envPath |
    Where-Object { $_.StartsWith($prefix, [System.StringComparison]::Ordinal) } |
    Select-Object -First 1

  if ($null -eq $line) {
    return $null
  }

  return $line.Substring($prefix.Length).Trim()
}

function Write-SafeError {
  param(
    [Parameter(Mandatory)][string]$HttpStatus,
    [Parameter(Mandatory)][string]$Summary
  )

  [Console]::Error.WriteLine("HTTP status: $HttpStatus")
  [Console]::Error.WriteLine("Error: $Summary")
}

function Test-FieldValue {
  param([AllowNull()][object]$Value)

  return -not [string]::IsNullOrWhiteSpace("$Value")
}

function Get-ItemInfoNames {
  param([AllowNull()][object]$Value)

  return @($Value) |
    ForEach-Object { $_.name } |
    Where-Object { Test-FieldValue -Value $_ }
}

function Add-Count {
  param(
    [Parameter(Mandatory)][hashtable]$Counts,
    [Parameter(Mandatory)][string]$Value
  )

  if ($Counts.ContainsKey($Value)) {
    $Counts[$Value]++
  }
  else {
    $Counts[$Value] = 1
  }
}

if (-not (Test-Path -LiteralPath $envPath -PathType Leaf)) {
  Write-SafeError -HttpStatus 'not requested' -Summary '.env was not found.'
  exit 1
}

$apiId = Get-DotEnvValue -Name 'DMM_API_ID'
$affiliateId = Get-DotEnvValue -Name 'DMM_AFFILIATE_ID'

if ([string]::IsNullOrWhiteSpace($apiId) -or [string]::IsNullOrWhiteSpace($affiliateId)) {
  Write-SafeError -HttpStatus 'not requested' -Summary 'Required environment values are not configured.'
  exit 1
}

$parameters = [ordered]@{
  api_id       = $apiId
  affiliate_id = $affiliateId
  site         = 'FANZA'
  service      = 'digital'
  floor        = 'videoa'
  hits         = '50'
  sort         = $Sort
  output       = 'json'
}

$query = ($parameters.GetEnumerator() | ForEach-Object {
  '{0}={1}' -f [Uri]::EscapeDataString($_.Key), [Uri]::EscapeDataString($_.Value)
}) -join '&'

$requestUri = "https://api.dmm.com/affiliate/v3/ItemList?$query"
$handler = [System.Net.Http.HttpClientHandler]::new()
$client = [System.Net.Http.HttpClient]::new($handler)
$client.Timeout = [TimeSpan]::FromSeconds($timeoutSeconds)
$response = $null

try {
  $response = $client.GetAsync($requestUri).GetAwaiter().GetResult()
  $httpStatus = [int]$response.StatusCode

  if (-not $response.IsSuccessStatusCode) {
    Write-SafeError -HttpStatus $httpStatus -Summary 'The API returned a non-success response.'
    exit 1
  }

  $body = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()

  try {
    $payload = $body | ConvertFrom-Json
  }
  catch {
    Write-SafeError -HttpStatus $httpStatus -Summary 'The API response was not valid JSON.'
    exit 1
  }

  if ($null -eq $payload.result) {
    Write-SafeError -HttpStatus $httpStatus -Summary 'The API response did not contain a result.'
    exit 1
  }

  $result = $payload.result

  if (("{0}" -f $result.status) -ne '200') {
    Write-SafeError -HttpStatus $httpStatus -Summary 'The API reported an unsuccessful status.'
    exit 1
  }

  if ($null -eq $result.items) {
    Write-SafeError -HttpStatus $httpStatus -Summary 'The API response did not contain items.'
    exit 1
  }

  $items = @($result.items)

  if ($items.Count -eq 0) {
    Write-SafeError -HttpStatus $httpStatus -Summary 'The API returned no items.'
    exit 1
  }

  $presence = [ordered]@{
    content_id       = 0
    product_id       = 0
    title            = 0
    date             = 0
    'prices.price'   = 0
    'review.average' = 0
    'review.count'   = 0
    maker            = 0
    series           = 0
    actress          = 0
    genre            = 0
    'imageURL.large' = 0
    URL              = 0
    affiliateURL     = 0
  }
  $priceCounts = @{}
  $makerCounts = @{}
  $dates = [System.Collections.Generic.List[string]]::new()
  $genreElementCounts = [System.Collections.Generic.List[int]]::new()
  $reviewMissingCount = 0

  foreach ($item in $items) {
    $makerNames = @(Get-ItemInfoNames -Value $item.iteminfo.maker)
    $seriesNames = @(Get-ItemInfoNames -Value $item.iteminfo.series)
    $actressNames = @(Get-ItemInfoNames -Value $item.iteminfo.actress)
    $genreNames = @(Get-ItemInfoNames -Value $item.iteminfo.genre)

    if (Test-FieldValue -Value $item.content_id) { $presence.content_id++ }
    if (Test-FieldValue -Value $item.product_id) { $presence.product_id++ }
    if (Test-FieldValue -Value $item.title) { $presence.title++ }
    if (Test-FieldValue -Value $item.date) {
      $presence.date++
      $dates.Add("$($item.date)")
    }
    if (Test-FieldValue -Value $item.prices.price) {
      $presence.'prices.price'++
      Add-Count -Counts $priceCounts -Value "$($item.prices.price)"
    }
    if ($null -ne $item.review -and (Test-FieldValue -Value $item.review.average)) {
      $presence.'review.average'++
    }
    if ($null -ne $item.review -and (Test-FieldValue -Value $item.review.count)) {
      $presence.'review.count'++
    }
    if ($null -eq $item.review) { $reviewMissingCount++ }
    if ($makerNames.Count -gt 0) {
      $presence.maker++
      foreach ($name in $makerNames) { Add-Count -Counts $makerCounts -Value "$name" }
    }
    if ($seriesNames.Count -gt 0) { $presence.series++ }
    if ($actressNames.Count -gt 0) { $presence.actress++ }
    if ($genreNames.Count -gt 0) { $presence.genre++ }
    $genreElementCounts.Add($genreNames.Count)
    if (Test-FieldValue -Value $item.imageURL.large) { $presence.'imageURL.large'++ }
    if (Test-FieldValue -Value $item.URL) { $presence.URL++ }
    if (Test-FieldValue -Value $item.affiliateURL) { $presence.affiliateURL++ }
  }

  Write-Output ("sort: {0}" -f $Sort)
  Write-Output ("status: {0}" -f $result.status)
  Write-Output ("result_count: {0}" -f $result.result_count)
  Write-Output ("processed_count: {0}" -f $items.Count)
  Write-Output '--- presence_counts ---'
  foreach ($entry in $presence.GetEnumerator()) {
    Write-Output ("{0}: {1}" -f $entry.Key, $entry.Value)
  }

  Write-Output '--- price_values_max_20 ---'
  $priceCounts.GetEnumerator() |
    Sort-Object -Property @{ Expression = 'Value'; Descending = $true }, @{ Expression = 'Key'; Descending = $false } |
    Select-Object -First 20 |
    ForEach-Object { Write-Output ("value: {0} | count: {1}" -f $_.Key, $_.Value) }

  Write-Output '--- maker_top_10 ---'
  $makerCounts.GetEnumerator() |
    Sort-Object -Property @{ Expression = 'Value'; Descending = $true }, @{ Expression = 'Key'; Descending = $false } |
    Select-Object -First 10 |
    ForEach-Object { Write-Output ("maker: {0} | count: {1}" -f $_.Key, $_.Value) }

  $sortedDates = @($dates | Sort-Object)
  $sortedGenreCounts = @($genreElementCounts | Sort-Object)

  Write-Output '--- missing_and_ranges ---'
  Write-Output ("series_missing_count: {0}" -f ($items.Count - $presence.series))
  Write-Output ("actress_missing_count: {0}" -f ($items.Count - $presence.actress))
  Write-Output ("review_missing_count: {0}" -f $reviewMissingCount)
  Write-Output ("genre_element_count_min: {0}" -f $sortedGenreCounts[0])
  Write-Output ("genre_element_count_max: {0}" -f $sortedGenreCounts[-1])
  Write-Output ("date_min: {0}" -f $sortedDates[0])
  Write-Output ("date_max: {0}" -f $sortedDates[-1])
}
catch [System.Threading.Tasks.TaskCanceledException] {
  Write-SafeError -HttpStatus 'unavailable' -Summary 'The API request timed out.'
  exit 1
}
catch {
  Write-SafeError -HttpStatus 'unavailable' -Summary 'The API request failed.'
  exit 1
}
finally {
  if ($null -ne $response) {
    $response.Dispose()
  }

  $client.Dispose()
  $handler.Dispose()
}
