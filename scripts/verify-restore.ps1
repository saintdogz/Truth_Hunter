param(
    [string]$BackupFile = ""
)

$ErrorActionPreference = "Stop"
$workspace = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $workspace

if (-not $BackupFile) {
    $BackupFile = Get-ChildItem -LiteralPath (Join-Path $workspace "backups") `
        -Filter "truthhunter-*.dump.enc" -File |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1 -ExpandProperty Name
}
if (-not $BackupFile -or $BackupFile -notmatch '^truthhunter-\d{8}T\d{6}Z\.dump\.enc$') {
    throw "Select a valid Truth Hunter encrypted backup filename."
}

$containerPath = "/backups/$BackupFile"
docker compose --profile operations run --rm backup restore $containerPath `
    --target-database truthhunter_restore_test
if ($LASTEXITCODE -ne 0) {
    throw "Truth Hunter restore verification failed with exit code $LASTEXITCODE"
}

$sourceCounts = docker compose exec -T postgres psql -U truthhunter -d truthhunter `
    -tA -c "SELECT (SELECT count(*) FROM users)||':'||(SELECT count(*) FROM investigations);"
$restoredCounts = docker compose exec -T postgres psql -U truthhunter `
    -d truthhunter_restore_test -tA `
    -c "SELECT (SELECT count(*) FROM users)||':'||(SELECT count(*) FROM investigations);"
if ($LASTEXITCODE -ne 0 -or $sourceCounts.Trim() -ne $restoredCounts.Trim()) {
    throw "Restored database integrity counts do not match the source database."
}

Write-Output "Restore verified successfully: $($restoredCounts.Trim())"
docker compose exec -T postgres dropdb --if-exists --force -U truthhunter `
    truthhunter_restore_test
if ($LASTEXITCODE -ne 0) {
    throw "Restore verified, but cleanup of truthhunter_restore_test failed."
}
