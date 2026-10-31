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
function Exec-Setup([string]$exe,[string[]]$SetupArgs){
  $p=Start-Process -FilePath $exe -ArgumentList $SetupArgs -Wait -PassThru
  if($p.ExitCode -ne 0){throw "NSIS_EXIT_$($p.ExitCode):$exe $($SetupArgs -join ' ')"}
}
# G5A: BuildID is the immutable runId sealed in each installed payload manifest.
# This reads the ACTUAL installed files on the disposable Windows runner;
# installer source-only tests must never substitute for this evidence.
function Get-InstalledBuildEvidence([string]$Phase) {
  $manifestFile=Join-Path $root 'payload.sha256.json'
  if (-not (Test-Path -LiteralPath $manifestFile -PathType Leaf)) { throw "NSIS_$($Phase)_MANIFEST_MISSING" }
  $m=Get-Content -LiteralPath $manifestFile -Raw -Encoding UTF8 | ConvertFrom-Json -ErrorAction Stop
  if ($m.schema -cne 'NOX_P01_PAYLOAD_SHA256_V1' -or
      $m.entrypoint -cne 'NOX.P01.Shell.exe' -or
      [string]$m.runId -cnotmatch '\A[A-Za-z0-9][A-Za-z0-9._:-]{1,127}\z') {
    throw "NSIS_$($Phase)_BUILDID_CONTRACT_INVALID"
  }
  $actual=@{}
  foreach($rel in @('NOX.P01.Shell.exe','Backend/NOX_HELION_PRIVATE_CANDIDATE.exe')) {
    $matches=@($m.files | Where-Object { [string]$_.path -ieq $rel })
    if ($matches.Count -ne 1) { throw "NSIS_$($Phase)_SINGLE_PAYLOAD_ENTRY_REQUIRED:$rel" }
    $expected=[string]$matches[0].sha256
    if ($expected -cnotmatch '\A[a-fA-F0-9]{64}\z') { throw "NSIS_$($Phase)_SHA_MALFORMED:$rel" }
    $file=Join-Path $root ($rel.Replace('/','\'))
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "NSIS_$($Phase)_FILE_MISSING:$rel" }
    $digest=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($digest -cne $expected.ToLowerInvariant()) { throw "NSIS_$($Phase)_FILE_SHA_DRIFT:$rel" }
    $actual[$rel]=$digest
  }
  return [pscustomobject]@{
    BuildId=([string]$m.runId)
    ManifestSha256=(Get-FileHash -LiteralPath $manifestFile -Algorithm SHA256).Hash.ToLowerInvariant()
    WpfExeSha256=$actual['NOX.P01.Shell.exe']
    BackendExeSha256=$actual['Backend/NOX_HELION_PRIVATE_CANDIDATE.exe']
  }
}
try {
  Exec-Setup $InitialSetup @('/S')
  if (-not (Test-Path -LiteralPath (Join-Path $root 'nox-p01-owned.txt'))) {throw 'FIRST_INSTALL_MARKER_MISSING'}
  $firstManifest=(Get-FileHash -LiteralPath (Join-Path $root 'payload.sha256.json') -Algorithm SHA256).Hash.ToLowerInvariant()
  $initialEvidence=Get-InstalledBuildEvidence 'INSTALL'
  if ($initialEvidence.ManifestSha256 -cne $firstManifest) {throw 'INITIAL_MANIFEST_EVIDENCE_DRIFT'}
  $results.initialBuildId=$initialEvidence.BuildId
  $results.initialWpfExeSha256=$initialEvidence.WpfExeSha256
  $results.initialBackendExeSha256=$initialEvidence.BackendExeSha256
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
  $upgradeEvidence=Get-InstalledBuildEvidence 'UPDATE'
  if ($upgradeEvidence.ManifestSha256 -cne $upgradeManifest) {throw 'UPGRADE_MANIFEST_EVIDENCE_DRIFT'}
  if ($upgradeEvidence.BuildId -ceq $initialEvidence.BuildId) {throw 'UPDATE_REUSED_INITIAL_BUILDID'}
  $results.upgradeBuildId=$upgradeEvidence.BuildId
  $results.upgradeWpfExeSha256=$upgradeEvidence.WpfExeSha256
  $results.upgradeBackendExeSha256=$upgradeEvidence.BackendExeSha256
  $results.update='PASS'
  # Negative regression: a corrupt prior payload MUST NOT be activated.
  # Mutate one byte in this disposable CI install, restore it in finally.
  $backupExe=Join-Path $backup 'NOX.P01.Shell.exe'
  if(-not (Test-Path -LiteralPath $backupExe -PathType Leaf)) {throw 'BACKUP_EXE_MISSING_FOR_NEGATIVE'}
  $backupExeSha=(Get-FileHash -LiteralPath $backupExe -Algorithm SHA256).Hash.ToLowerInvariant()
  $stream=[IO.File]::Open($backupExe,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
  $byteBefore=-1
  try {
    $byteBefore=$stream.ReadByte()
    if ($byteBefore -lt 0) {throw 'EMPTY_BACKUP_EXE'}
    [void]$stream.Seek(0,[IO.SeekOrigin]::Begin)
    $stream.WriteByte([byte]($byteBefore -bxor 1))
    $stream.Flush($true)
  } finally { $stream.Dispose() }
  try {
    $errorOnCorrupt=$null
    try { Exec-Setup $UpgradeSetup @('/S','/ROLLBACK') }
    catch { $errorOnCorrupt=$_.ToString() }
    if (-not $errorOnCorrupt) {throw 'CORRUPT_BACKUP_WAS_ACCEPTED'}
    if (-not (Test-Path -LiteralPath $backupExe -PathType Leaf) -or
        -not (Test-Path -LiteralPath (Join-Path $root 'nox-p01-owned.txt')) -or
        (Test-Path -LiteralPath $rollbackSaved)) {
      throw 'CORRUPT_BACKUP_CHANGED_APPLICATION_DIRS'
    }
    if ((Get-FileHash -LiteralPath (Join-Path $root 'payload.sha256.json') -Algorithm SHA256).Hash.ToLowerInvariant() -cne $upgradeManifest) {
      throw 'CORRUPT_BACKUP_CHANGED_CURRENT_PAYLOAD'
    }
  } finally {
    $stream=[IO.File]::Open($backupExe,[IO.FileMode]::Open,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
    try {
      [void]$stream.Seek(0,[IO.SeekOrigin]::Begin)
      $stream.WriteByte([byte]$byteBefore)
      $stream.Flush($true)
    } finally { $stream.Dispose() }
  }
  if ((Get-FileHash -LiteralPath $backupExe -Algorithm SHA256).Hash.ToLowerInvariant() -cne $backupExeSha) {
    throw 'BACKUP_NEGATIVE_TEST_DID_NOT_RESTORE_EXACT_BYTES'
  }
  $results.corruptBackupRejected='PASS'
  Exec-Setup $UpgradeSetup @('/S','/ROLLBACK')
  if(-not (Test-Path -LiteralPath (Join-Path $rollbackSaved 'nox-p01-owned.txt'))) {throw 'ROLLED_BACK_NEWER_APP_NOT_RETAINED'}
  if((Get-FileHash -LiteralPath (Join-Path $root 'payload.sha256.json') -Algorithm SHA256).Hash.ToLowerInvariant() -cne $firstManifest){throw 'ROLLBACK_VERSION_NOT_RESTORED'}
  if ((Get-FileHash -LiteralPath (Join-Path $rollbackSaved 'payload.sha256.json') -Algorithm SHA256).Hash.ToLowerInvariant() -cne $upgradeManifest) {
    throw 'ROLLBACK_SAVED_NEW_VERSION_DRIFT'
  }
  $rollbackEvidence=Get-InstalledBuildEvidence 'ROLLBACK'
  if ($rollbackEvidence.BuildId -cne $initialEvidence.BuildId -or
      $rollbackEvidence.ManifestSha256 -cne $firstManifest -or
      $rollbackEvidence.WpfExeSha256 -cne $initialEvidence.WpfExeSha256 -or
      $rollbackEvidence.BackendExeSha256 -cne $initialEvidence.BackendExeSha256) {
    throw 'ROLLBACK_BUILDID_OR_BINARY_SHA_MISMATCH'
  }
  $results.rollbackBuildId=$rollbackEvidence.BuildId
  $results.rollbackWpfExeSha256=$rollbackEvidence.WpfExeSha256
  $results.rollbackBackendExeSha256=$rollbackEvidence.BackendExeSha256
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
