# P01 E01 C5 · native transactional acceptance for isolated, disposable Windows x64 runner.
# This script is NEVER run automatically by the app or by the C5 source package.
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$InitialSetup,
  [Parameter(Mandatory=$true)][string]$UpgradeSetup,
  [Parameter(Mandatory=$true)][string]$ExpectedInitialSetupSha256,
  [Parameter(Mandatory=$true)][string]$ExpectedUpgradeSetupSha256,
  [Parameter(Mandatory=$true)][string]$ReportPath,
  [switch]$DisposableRunnerAcknowledged
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if (-not $DisposableRunnerAcknowledged -or $env:CI -ne 'true') { throw 'DISPOSABLE_CI_RUNNER_REQUIRED' }
if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitOperatingSystem) { throw 'WINDOWS_X64_REQUIRED' }
$root=Join-Path $env:LOCALAPPDATA 'Programs\NOX HELION'
$backup="$root.__p01_previous"
$stage="$root.__p01_stage"
$rollbackSaved="$root.__p01_rollback_saved"
$userData=Join-Path $env:LOCALAPPDATA 'NOX_HELION\P01'
foreach($path in @($root,$backup,$stage,$rollbackSaved,$userData)) {
  if(Test-Path -LiteralPath $path) { throw "DISPOSABLE_RUNNER_NOT_EMPTY:$path" }
}
foreach($pair in @(@($InitialSetup,$ExpectedInitialSetupSha256),@($UpgradeSetup,$ExpectedUpgradeSetupSha256))) {
  $file=[IO.Path]::GetFullPath($pair[0]);$want=([string]$pair[1]).ToLowerInvariant()
  if ($want -notmatch '^[0-9a-f]{64}$') {throw 'EXPECTED_SETUP_SHA256_INVALID'}
  if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {throw "SETUP_MISSING:$file"}
  if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -cne $want) {throw "SETUP_SHA256_MISMATCH:$file"}
}
if ($ExpectedInitialSetupSha256.ToLowerInvariant() -ceq $ExpectedUpgradeSetupSha256.ToLowerInvariant()) {throw 'UPGRADE_SETUP_BINARY_NOT_DISTINCT'}
$results=[ordered]@{schema='NOX_P01_NSIS_NATIVE_QA_V1'; timestampUTC=[DateTime]::UtcNow.ToString('o');runId=$env:GITHUB_RUN_ID; machine=$env:COMPUTERNAME; firstSetupSha256=$ExpectedInitialSetupSha256; upgradeSetupSha256=$ExpectedUpgradeSetupSha256; install='NOT_RUN'; update='NOT_RUN';rollback='NOT_RUN';uninstall='NOT_RUN'; userDataRetained='NOT_RUN'; releaseAllowed=$false}
function Exec-Setup([string]$exe,[string[]]$args){
  $p=Start-Process -FilePath $exe -ArgumentList $args -Wait -PassThru
  if($p.ExitCode -ne 0){throw "NSIS_EXIT_$($p.ExitCode):$exe $($args -join ' ')"}
}
try {
  Exec-Setup $InitialSetup @('/S')
  if (-not (Test-Path -LiteralPath (Join-Path $root 'nox-p01-owned.txt'))) {throw 'FIRST_INSTALL_MARKER_MISSING'}
  $firstManifest=(Get-FileHash -LiteralPath (Join-Path $root 'payload.sha256.json') -Algorithm SHA256).Hash.ToLowerInvariant()
  $results.install='PASS'
  New-Item -ItemType Directory -Path $userData -Force | Out-Null
  $sentinel=Join-Path $userData 'E01_C5_NSDATA_KEEP.txt'
  $sentinelText='C5 NSIS QA data must survive update, rollback and uninstall.'
  [IO.File]::WriteAllText($sentinel,$sentinelText)
  $sentinelHash=(Get-FileHash -LiteralPath $sentinel -Algorithm SHA256).Hash.ToLowerInvariant()
  Exec-Setup $UpgradeSetup @('/S')
  if (-not (Test-Path -LiteralPath (Join-Path $backup 'nox-p01-owned.txt'))) {throw 'BACKUP_NOT_RETAINED'}
  if (-not (Test-Path -LiteralPath (Join-Path $root 'nox-p01-owned.txt'))) {throw 'UPGRADED_APP_MISSING'}
  if ((Get-FileHash -LiteralPath (Join-Path $backup 'payload.sha256.json') -Algorithm SHA256).Hash.ToLowerInvariant() -cne $firstManifest){throw 'BACKUP_MANIFEST_DRIFT'}
  $upgradeManifest=(Get-FileHash -LiteralPath (Join-Path $root 'payload.sha256.json') -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($upgradeManifest -ceq $firstManifest) { throw 'UPGRADE_PAYLOAD_NOT_DISTINCT' }
  $results.update='PASS'
  Exec-Setup $UpgradeSetup @('/S','/ROLLBACK')
  if(-not (Test-Path -LiteralPath (Join-Path $rollbackSaved 'nox-p01-owned.txt'))) {throw 'ROLLED_BACK_NEWER_APP_NOT_RETAINED'}
  if((Get-FileHash -LiteralPath (Join-Path $root 'payload.sha256.json') -Algorithm SHA256).Hash.ToLowerInvariant() -cne $firstManifest){throw 'ROLLBACK_VERSION_NOT_RESTORED'}
  if ((Get-FileHash -LiteralPath (Join-Path $rollbackSaved 'payload.sha256.json') -Algorithm SHA256).Hash.ToLowerInvariant() -cne $upgradeManifest) {
    throw 'ROLLBACK_SAVED_NEW_VERSION_DRIFT'
  }
  $results.rollback='PASS'
  Exec-Setup (Join-Path $root 'Uninstall.exe') @('/S')
  if(Test-Path -LiteralPath (Join-Path $root 'nox-p01-owned.txt')) {throw 'UNINSTALL_OWNERSHIP_MARKER_REMAINS'}
  $results.uninstall='PASS'
  if((Get-FileHash -LiteralPath $sentinel -Algorithm SHA256).Hash.ToLowerInvariant() -cne $sentinelHash){throw 'USER_DATA_SENTINEL_CHANGED'}
  $results.userDataRetained='PASS'
  # This is a native installer component test, not the independent E07 acceptance.
  $results.releaseAllowed=$false
}catch{
  $results.error=$_.ToString()
  throw
}finally{
  $results.timestampEndUTC=[DateTime]::UtcNow.ToString('o')
  New-Item -ItemType Directory -Path (Split-Path -Parent $ReportPath) -Force | Out-Null
  [IO.File]::WriteAllText([IO.Path]::GetFullPath($ReportPath),($results|ConvertTo-Json -Depth 6))
}
