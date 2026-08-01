param(
    [Parameter(Mandatory = $true)][string]$DsnSecretPath,
    [Parameter(Mandatory = $true)][string]$DestinationDirectory
)

$ErrorActionPreference = "Stop"
$secretPath = (Resolve-Path -LiteralPath $DsnSecretPath).Path
if (-not (Test-Path -LiteralPath $DestinationDirectory)) {
    New-Item -ItemType Directory -Path $DestinationDirectory | Out-Null
}
$destination = (Resolve-Path -LiteralPath $DestinationDirectory).Path
$timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$backupPath = Join-Path $destination "decision-assurance-$timestamp.dump"
$manifestPath = Join-Path $destination "backup-manifest.json"
$databaseDsn = (Get-Content -LiteralPath $secretPath -Raw).Trim()
if ([string]::IsNullOrWhiteSpace($databaseDsn)) { throw "BACKUP_DSN_UNAVAILABLE" }

& pg_dump --dbname=$databaseDsn --format=custom --compress=9 --no-owner --file=$backupPath
if ($LASTEXITCODE -ne 0) { throw "PG_DUMP_FAILED" }

$file = Get-Item -LiteralPath $backupPath
$checksum = (Get-FileHash -LiteralPath $backupPath -Algorithm SHA256).Hash.ToLowerInvariant()
$manifest = [ordered]@{
    schema_version = "0.5.0"
    database_schema_version = "003"
    created_at = (Get-Date).ToUniversalTime().ToString("o")
    backup_file = $file.Name
    format = "postgresql-custom"
    size_bytes = $file.Length
    sha256 = $checksum
    storage_encryption_required = $true
}
$manifest | ConvertTo-Json | Set-Content -LiteralPath $manifestPath -Encoding utf8NoBOM
$databaseDsn = $null
Write-Output $manifestPath
