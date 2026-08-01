param(
    [Parameter(Mandatory = $true)][string]$DsnSecretPath,
    [Parameter(Mandatory = $true)][string]$ManifestPath
)

$ErrorActionPreference = "Stop"
$secretPath = (Resolve-Path -LiteralPath $DsnSecretPath).Path
$manifestFile = (Resolve-Path -LiteralPath $ManifestPath).Path
$manifest = Get-Content -LiteralPath $manifestFile -Raw | ConvertFrom-Json
$backupPath = Join-Path (Split-Path -Parent $manifestFile) $manifest.backup_file
if (-not (Test-Path -LiteralPath $backupPath)) { throw "BACKUP_FILE_MISSING" }
$actualChecksum = (Get-FileHash -LiteralPath $backupPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualChecksum -ne $manifest.sha256) { throw "BACKUP_CHECKSUM_MISMATCH" }
if ($manifest.database_schema_version -ne "004") { throw "BACKUP_SCHEMA_INCOMPATIBLE" }

$databaseDsn = (Get-Content -LiteralPath $secretPath -Raw).Trim()
if ([string]::IsNullOrWhiteSpace($databaseDsn)) { throw "RESTORE_DSN_UNAVAILABLE" }
& pg_restore --dbname=$databaseDsn --exit-on-error --single-transaction --no-owner $backupPath
if ($LASTEXITCODE -ne 0) { throw "PG_RESTORE_FAILED" }

$env:DA_RESTORE_DSN = $databaseDsn
if ([string]::IsNullOrWhiteSpace($env:DA_RECOVERY_COMMIT_SHA)) { throw "DA_RECOVERY_COMMIT_SHA_REQUIRED" }
if ([string]::IsNullOrWhiteSpace($env:DA_RECOVERY_ENVIRONMENT)) { throw "DA_RECOVERY_ENVIRONMENT_REQUIRED" }
if ([string]::IsNullOrWhiteSpace($env:DA_RECOVERY_SOURCE_DATABASE)) { throw "DA_RECOVERY_SOURCE_DATABASE_REQUIRED" }
& python (Join-Path $PSScriptRoot "verify_restore.py")
if ($LASTEXITCODE -ne 0) { throw "RESTORE_VERIFICATION_FAILED" }
Remove-Item Env:DA_RESTORE_DSN
$databaseDsn = $null
