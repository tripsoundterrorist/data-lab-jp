[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$timeoutSeconds = 15
$envPath = Join-Path (Split-Path -Parent $PSScriptRoot) '.env'

function Get-DotEnvValue {
  param(
    [Parameter(Mandatory)]
    [string]$Name
  )

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
    [Parameter(Mandatory)]
    [string]$HttpStatus,

    [Parameter(Mandatory)]
    [string]$Summary
  )

  [Console]::Error.WriteLine("HTTP status: $HttpStatus")
  [Console]::Error.WriteLine("Error: $Summary")
}

function Get-ItemInfoNames {
  param(
    [AllowNull()]
    [object]$Value
  )

  return @($Value) |
    ForEach-Object { $_.name } |
    Where-Object { -not [string]::IsNullOrWhiteSpace("$_") }
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
  hits         = '10'
  sort         = 'date'
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

  Write-Output ("status: {0}" -f $result.status)
  Write-Output ("result_count: {0}" -f $result.result_count)

  $priceCount = 0
  $reviewAverageCount = 0
  $reviewCountCount = 0
  $dateCount = 0
  $makerCount = 0
  $seriesCount = 0
  $actressCount = 0
  $genreCount = 0
  $imageLargeCount = 0
  $urlCount = 0
  $affiliateUrlCount = 0

  for ($index = 0; $index -lt $items.Count; $index++) {
    $item = $items[$index]
    $makerNames = @(Get-ItemInfoNames -Value $item.iteminfo.maker)
    $seriesNames = @(Get-ItemInfoNames -Value $item.iteminfo.series)
    $actressNames = @(Get-ItemInfoNames -Value $item.iteminfo.actress)
    $genreNames = @(Get-ItemInfoNames -Value $item.iteminfo.genre)

    Write-Output ("--- item {0} ---" -f ($index + 1))
    Write-Output ("content_id: {0}" -f $item.content_id)
    Write-Output ("product_id: {0}" -f $item.product_id)
    Write-Output ("title: {0}" -f $item.title)
    Write-Output ("price: {0}" -f $item.prices.price)

    if ($null -ne $item.prices -and $null -ne $item.prices.price) {
      $priceCount++
    }

    if ($null -ne $item.review -and $null -ne $item.review.average) {
      Write-Output ("review.average: {0}" -f $item.review.average)
      $reviewAverageCount++
    }

    if ($null -ne $item.review -and $null -ne $item.review.count) {
      Write-Output ("review.count: {0}" -f $item.review.count)
      $reviewCountCount++
    }

    if (-not [string]::IsNullOrWhiteSpace("$($item.date)")) {
      Write-Output ("date: {0}" -f $item.date)
      $dateCount++
    }

    if ($makerNames.Count -gt 0) {
      Write-Output ("maker: {0}" -f ($makerNames -join ', '))
      $makerCount++
    }

    if ($seriesNames.Count -gt 0) {
      Write-Output ("series: {0}" -f ($seriesNames -join ', '))
      $seriesCount++
    }

    if ($actressNames.Count -gt 0) {
      Write-Output ("actress: {0}" -f ($actressNames -join ', '))
      $actressCount++
    }

    if ($genreNames.Count -gt 0) {
      Write-Output ("genre: {0}" -f ($genreNames -join ', '))
      $genreCount++
    }

    if (-not [string]::IsNullOrWhiteSpace("$($item.imageURL.large)")) {
      Write-Output ("imageURL.large: {0}" -f $item.imageURL.large)
      $imageLargeCount++
    }

    if (-not [string]::IsNullOrWhiteSpace("$($item.URL)")) {
      Write-Output ("URL: {0}" -f $item.URL)
      $urlCount++
    }

    if (-not [string]::IsNullOrWhiteSpace("$($item.affiliateURL)")) {
      Write-Output 'affiliateURL: 存在する'
      $affiliateUrlCount++
    }
    else {
      Write-Output 'affiliateURL: 存在しない'
    }
  }

  Write-Output '--- summary ---'
  Write-Output ("processed_count: {0}" -f $items.Count)
  Write-Output ("price_count: {0}" -f $priceCount)
  Write-Output ("review.average_count: {0}" -f $reviewAverageCount)
  Write-Output ("review.count_count: {0}" -f $reviewCountCount)
  Write-Output ("date_count: {0}" -f $dateCount)
  Write-Output ("maker_count: {0}" -f $makerCount)
  Write-Output ("series_count: {0}" -f $seriesCount)
  Write-Output ("actress_count: {0}" -f $actressCount)
  Write-Output ("genre_count: {0}" -f $genreCount)
  Write-Output ("imageURL.large_count: {0}" -f $imageLargeCount)
  Write-Output ("URL_count: {0}" -f $urlCount)
  Write-Output ("affiliateURL_count: {0}" -f $affiliateUrlCount)
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
