param(
    [string]$Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pythonPath = (Resolve-Path (Join-Path $projectRoot $Python)).Path
$uvPath = (Get-Command uv -ErrorAction Stop).Source
$buildRoot = [System.IO.Path]::GetFullPath((Join-Path $projectRoot ".local\build"))
$stage = [System.IO.Path]::GetFullPath((Join-Path $buildRoot "lambda-pv-stage"))
$artifact = [System.IO.Path]::GetFullPath((Join-Path $buildRoot "lambda_pv.zip"))
$rootPrefix = $projectRoot.TrimEnd('\') + '\'

foreach ($target in @($buildRoot, $stage, $artifact)) {
    if (-not $target.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to modify a build path outside the ElectionHub workspace: $target"
    }
}

if (Test-Path -LiteralPath $stage) {
    Remove-Item -LiteralPath $stage -Recurse -Force
}
if (Test-Path -LiteralPath $artifact) {
    Remove-Item -LiteralPath $artifact -Force
}

New-Item -ItemType Directory -Force -Path (Join-Path $stage "app") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $stage "certs") | Out-Null

& $uvPath pip install `
    --link-mode copy `
    --python-platform x86_64-manylinux2014 `
    --python-version 3.11 `
    --only-binary=:all: `
    --requirement (Join-Path $projectRoot "infra\aws\lambda\pv\requirements.txt") `
    --target $stage
if ($LASTEXITCODE -ne 0) {
    throw "Lambda dependency installation failed."
}

Copy-Item -LiteralPath (Join-Path $projectRoot "backend\app\__init__.py") `
    -Destination (Join-Path $stage "app\__init__.py")
Copy-Item -LiteralPath (Join-Path $projectRoot "backend\app\lambda_pv.py") `
    -Destination (Join-Path $stage "app\lambda_pv.py")

$caPath = Join-Path $stage "certs\eu-north-1-bundle.pem"
Invoke-WebRequest `
    -Uri "https://truststore.pki.rds.amazonaws.com/eu-north-1/eu-north-1-bundle.pem" `
    -OutFile $caPath `
    -UseBasicParsing

& $pythonPath -c "import ssl,sys; ssl.create_default_context(cafile=sys.argv[1])" $caPath
if ($LASTEXITCODE -ne 0) {
    throw "The downloaded RDS CA bundle is invalid."
}

Compress-Archive -Path (Join-Path $stage "*") -DestinationPath $artifact -CompressionLevel Optimal
& $pythonPath -c `
    "import sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); required={'app/lambda_pv.py','certs/eu-north-1-bundle.pem'}; missing=required-set(z.namelist()); assert not missing, missing" `
    $artifact
if ($LASTEXITCODE -ne 0) {
    throw "The Lambda artifact is incomplete."
}

$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $artifact).Hash.ToLowerInvariant()
Write-Output "Built $artifact"
Write-Output "SHA256 $hash"
