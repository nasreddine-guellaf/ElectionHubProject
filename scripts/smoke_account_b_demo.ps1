param(
    [Parameter(Mandatory)][string]$Profile,
    [Parameter(Mandatory)][ValidatePattern('^[0-9]{12}$')][string]$AccountId,
    [string]$Region = "eu-north-1"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$identity = aws sts get-caller-identity --profile $Profile --region $Region --output json --no-cli-pager
if ($LASTEXITCODE -ne 0 -or ($identity | Out-String | ConvertFrom-Json).Account -ne $AccountId) {
    throw "AWS identity did not match the verified Account B ID."
}

$outputDir = Join-Path $projectRoot ".local/aws-account-b"
New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
foreach ($kind in @("pv", "otp")) {
    $fixture = Join-Path $projectRoot "infra/aws-account-b/events/$kind.json"
    $responsePath = Join-Path $outputDir "$kind-smoke.json"
    $invoke = aws lambda invoke --profile $Profile --region $Region `
        --function-name "electionhub-b-demo-$kind" --invocation-type RequestResponse `
        --payload "fileb://$fixture" --output json --no-cli-pager $responsePath
    if ($LASTEXITCODE -ne 0) {
        throw "$kind demo invocation failed."
    }
    $metadata = $invoke | Out-String | ConvertFrom-Json
    if ($metadata.StatusCode -ne 200 -or $metadata.FunctionError) {
        throw "$kind demo returned a Lambda invocation error."
    }
    $response = Get-Content -Raw -LiteralPath $responsePath | ConvertFrom-Json
    $propertyCount = @($response.PSObject.Properties).Count
    if ($kind -eq "pv") {
        if ($propertyCount -ne 3 -or $response.processed -ne 1 -or
            $response.duplicate -ne 1 -or $response.failed -ne 0) {
            throw "Unexpected PV demo response."
        }
    } elseif ($propertyCount -ne 2 -or $response.version -ne 1 -or $response.status -ne "accepted") {
        throw "Unexpected OTP demo response."
    }
    Write-Output "$kind smoke test passed"
}
