param()

$ErrorActionPreference = "Stop"
$workspace = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $workspace

docker compose --profile operations run --rm backup backup
if ($LASTEXITCODE -ne 0) {
    throw "Truth Hunter backup failed with exit code $LASTEXITCODE"
}
