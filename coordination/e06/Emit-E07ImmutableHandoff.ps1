# E07-BLOCK-01/04: one immutable release identity; not a second ZIP validator.
[CmdletBinding()]
param(
 [Parameter(Mandatory=$true)][string]$Original729Receipt,
 [Parameter(Mandatory=$true)][string]$Owner729Receipt,
 [Parameter(Mandatory=$true)][string]$OneHostReceipt,
 [Parameter(Mandatory=$true)][string]$SetupExe,
 [Parameter(Mandatory=$true)][string]$PublishedExe,
 [Parameter(Mandatory=$true)][string]$SourceCommitSha,
 [Parameter(Mandatory=$true)][string]$Output,
 [ValidateSet('BUILT','INSTALLED')][string]$Phase='BUILT',
 [string]$InstalledExe='',
 [string]$InstallLog='',
 [string]$LaunchLog='',
 [string]$UpdateLog='',
 [string]$RollbackLog='',
 [string]$UninstallLog=''
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
# Reject a reparse point anywhere in the artifact or receipt ancestry, not
# only the leaf. A redirected parent can otherwise escape the frozen BuildID.
function AssertE07NoReparseAncestors([string]$path) {
 $cursor=[IO.Path]::GetFullPath($path)
 while ($true) {
  if (Test-Path -LiteralPath $cursor) {
   $node=Get-Item -LiteralPath $cursor -Force
   if (($node.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw "E07_REPARSE_ANCESTOR:$cursor"
   }
  }
  $parent=[IO.Path]::GetDirectoryName($cursor)
  if ([string]::IsNullOrWhiteSpace($parent) -or $parent -ceq $cursor) { break }
  $cursor=$parent
 }
}
function FileSha([string]$path) {
 AssertE07NoReparseAncestors $path
 if (!(Test-Path -LiteralPath $path -PathType Leaf)) { throw "E07_FILE_MISSING:$path" }
 $item=Get-Item -LiteralPath $path -Force
 if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
   throw "E07_REPARSE_INPUT:$path"
 }
 return (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
}
$commit=$SourceCommitSha.ToLowerInvariant()
if ($commit -cnotmatch '^[0-9a-f]{40}$') { throw 'E07_SOURCE_COMMIT_INVALID' }
# Resolve HEAD from this immutable in-repository entrypoint, never caller CWD.
$e07RepoRoot=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
$head=((& git -C $e07RepoRoot rev-parse HEAD) | Out-String).Trim().ToLowerInvariant()
if ($LASTEXITCODE -ne 0 -or $head -cne $commit) { throw 'E07_CHECKOUT_SHA_DRIFT' }
$manifestSha=FileSha $Original729Receipt
$ownerSha=FileSha $Owner729Receipt
$onehostSha=FileSha $OneHostReceipt
$setupSha=FileSha $SetupExe
$exeSha=FileSha $PublishedExe
$source=Get-Content -LiteralPath $Original729Receipt -Raw -Encoding UTF8 | ConvertFrom-Json
$owner=Get-Content -LiteralPath $Owner729Receipt -Raw -Encoding UTF8 | ConvertFrom-Json
$onehost=Get-Content -LiteralPath $OneHostReceipt -Raw -Encoding UTF8 | ConvertFrom-Json
if ($source.schema -cne 'NOX_ORIGINAL_SOURCE_729_SHA256_V1' -or
 $source.status -cne 'SOURCE_ARCHIVE_VERIFIED_ONLY_NOT_E07_RELEASE' -or
 $source.zip_bytes -ne 60364346 -or
 $source.zip_sha256 -cne 'ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a' -or
 $source.file_count -ne 729 -or @($source.files).Count -ne 729 -or
 @($source.parts).Count -ne 3) { throw 'E07_ORIGINAL_729_SOURCELOCK_NOT_VERIFIED' }
$paths=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($f in $source.files) {
 if ([string]::IsNullOrWhiteSpace([string]$f.path) -or
 !$paths.Add([string]$f.path) -or
 [string]$f.sha256 -cnotmatch '^[0-9a-f]{64}$') {
   throw 'E07_INVALID_ORIGINAL_SOURCE_RECEIPT'
 }
}
# Existing owner-specific and canonical 729 member SHA receipts must agree.
# This parity check does not create another ZIP validator or award E07 acceptance.
if ($owner.schema -cne 'NOX_V16_ORIGINAL_729_INNER_SHA256_SOURCELOCK_V1' -or
    $owner.status -cne 'ORIGINAL_ARCHIVE_BYTES_AND_INNER_FILES_VERIFIED_ONLY' -or
    $owner.fileCount -ne 729 -or @($owner.files).Count -ne 729 -or
    ([string]$owner.combinedZip.sha256).ToLowerInvariant() -cne
    ([string]$source.zip_sha256).ToLowerInvariant() -or
    $owner.combinedZip.bytes -ne $source.zip_bytes -or
    @($owner.combinedZip.sourceParts).Count -ne 3 -or
    $owner.nativeWindowsAccepted -ne $false -or $owner.releaseAccepted -ne $false) {
 throw 'E07_OWNER_729_SOURCELOCK_CONTRACT_MISMATCH'
}
$canonicalByPath=@{}
foreach ($f in $source.files) {
 $key=([string]$f.path).ToLowerInvariant()
 if ($canonicalByPath.ContainsKey($key)) { throw 'E07_CANONICAL_729_DUPLICATE_PATH' }
 $canonicalByPath[$key]=$f
}
$ownerSeen=[Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
foreach ($f in $owner.files) {
 $key=([string]$f.path).ToLowerInvariant()
 if ([string]::IsNullOrWhiteSpace($key) -or !$ownerSeen.Add($key) -or
     !$canonicalByPath.ContainsKey($key)) {
  throw 'E07_OWNER_729_PATH_SET_DIFFERS'
 }
 $matched=$canonicalByPath[$key]
 if ([string]$f.path -cne [string]$matched.path -or
     [long]$f.bytes -ne [long]$matched.bytes -or
     ([string]$f.sha256).ToLowerInvariant() -cne ([string]$matched.sha256).ToLowerInvariant()) {
  throw "E07_OWNER_729_FILE_SHA_DIFFERS:$key"
 }
}
if ($ownerSeen.Count -ne $canonicalByPath.Count) {
 throw 'E07_OWNER_729_FILE_SET_INCOMPLETE'
}
foreach ($expected in @($source.parts)) {
 $matching=@($owner.combinedZip.sourceParts | Where-Object {
  $_.path -ceq $expected.name -and $_.bytes -eq $expected.bytes
 })
 if ($matching.Count -ne 1 -or
     ([string]$matching[0].sha256) -cnotmatch '^[0-9a-f]{64}$' -or
     ([string]$expected.sha256) -cnotmatch '^[0-9a-f]{64}$' -or
     ([string]$matching[0].sha256).ToLowerInvariant() -cne ([string]$expected.sha256).ToLowerInvariant() -or
     ([string]$matching[0].gitBlobSha1) -cnotmatch '^[0-9a-f]{40}$' -or
     ([string]$expected.git_blob_sha1) -cnotmatch '^[0-9a-f]{40}$' -or
     ([string]$matching[0].gitBlobSha1).ToLowerInvariant() -cne ([string]$expected.git_blob_sha1).ToLowerInvariant()) {
  throw 'E07_OWNER_SOURCE_PART_IDENTITY_MISMATCH'
 }
}
if ($onehost.schema -cne 'NOX-E06-ONEHOST-DIAGNOSTIC-NSIS-v1' -or
 $onehost.release_accepted -ne $false -or
 ([string]$onehost.source_commit_sha1) -cne $commit -or
 ([string]$onehost.installer_sha256).ToLowerInvariant() -cne $setupSha -or
 ([string]$onehost.wpf_exe_sha256).ToLowerInvariant() -cne $exeSha) {
 throw 'E07_SETUP_EXE_RECEIPT_SHA_DRIFT'
}
$identity="$($source.zip_sha256)|$commit|$setupSha|$exeSha"
$hash=[Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($identity))
$buildId='NOX-V16-'+([Convert]::ToHexString($hash).ToLowerInvariant().Substring(0,24))
$installedSha=$null
$logs=[ordered]@{}
$logPaths=[ordered]@{}
if ($Phase -ceq 'INSTALLED') {
 if ([string]::IsNullOrWhiteSpace($InstalledExe)) { throw 'E07_INSTALLED_EXE_MISSING' }
 $installedSha=FileSha $InstalledExe
 if ($installedSha -cne $exeSha) { throw 'E07_INSTALLED_EXE_SHA_DRIFT' }
 foreach ($entry in @(
 @{name='install';file=$InstallLog},
 @{name='launch';file=$LaunchLog},
 @{name='update';file=$UpdateLog},
 @{name='rollback';file=$RollbackLog},
 @{name='uninstall';file=$UninstallLog})) {
  if ([string]::IsNullOrWhiteSpace($entry.file)) { throw "E07_LIFECYCLE_LOG_MISSING:$($entry.name)" }
  $logs[$entry.name]=FileSha $entry.file
  $logPaths[$entry.name]=$entry.file
  if ((Get-Item -LiteralPath $entry.file).Length -le 0) {
   throw "E07_LIFECYCLE_LOG_EMPTY:$($entry.name)"
  }
 }
}
# Reject any source receipt or binary mutation between admission and sealing.
if ((FileSha $Original729Receipt) -cne $manifestSha -or
    (FileSha $Owner729Receipt) -cne $ownerSha -or
    (FileSha $OneHostReceipt) -cne $onehostSha -or
    (FileSha $SetupExe) -cne $setupSha -or
    (FileSha $PublishedExe) -cne $exeSha) {
 throw 'E07_BUILD_INPUT_MUTATED_DURING_HANDOFF'
}
if ($Phase -ceq 'INSTALLED' -and
    (FileSha $InstalledExe) -cne $installedSha) {
 throw 'E07_INSTALLED_EXE_MUTATED_DURING_HANDOFF'
}
if ($Phase -ceq 'INSTALLED') {
 foreach ($name in @('install','launch','update','rollback','uninstall')) {
  if (!$logPaths.Contains($name) -or
      (FileSha ([string]$logPaths[$name])) -cne [string]$logs[$name]) {
   throw "E07_LIFECYCLE_LOG_MUTATED_DURING_HANDOFF:$name"
  }
 }
}
$receipt=[ordered]@{
 schema='NOX_V16_E07_IMMUTABLE_HANDOFF_V1'
 build_id=$buildId;phase=$Phase
 source_commit_sha1=$commit;original_zip_sha256=$source.zip_sha256
 original_manifest_sha256=$manifestSha;owner_729_manifest_sha256=$ownerSha;
 source_receipts_729_parity_verified=$true;source_files=729
 e06_onehost_receipt_sha256=$onehostSha
 setup_sha256=$setupSha;published_exe_sha256=$exeSha
 installed_exe_sha256=$installedSha;lifecycle_log_sha256=$logs
 # Presence of logs is not independent acceptance of their contents.
 independent_e07_cases_accepted=0
 release_accepted=$false
 status='PENDING_E07_INDEPENDENT_SAME_SHA_QA'
}
if (Test-Path -LiteralPath $Output) { throw 'E07_HANDOFF_ALREADY_EXISTS' }
$parent=Split-Path -Parent $Output
if ([string]::IsNullOrWhiteSpace($parent)) { throw 'E07_OUTPUT_PARENT_REQUIRED' }
# Check the complete output ancestry both before and after creating its parent.
# The no-clobber FileMode.CreateNew below remains the atomic output write.
AssertE07NoReparseAncestors $Output
New-Item -ItemType Directory -Path $parent -Force | Out-Null
AssertE07NoReparseAncestors $Output
# FileMode.CreateNew makes the no-clobber guarantee atomic across processes.
# Test-Path above is advisory only; the exclusive create is authoritative.
function WriteReceiptNoClobber([string]$path, [string]$content) {
 $bytes=[Text.UTF8Encoding]::new($false).GetBytes($content)
 $stream=[IO.FileStream]::new($path,[IO.FileMode]::CreateNew,
   [IO.FileAccess]::Write,[IO.FileShare]::None)
 try {
  $stream.Write($bytes,0,$bytes.Length)
  $stream.Flush($true)
 } finally {
  $stream.Dispose()
 }
}
# Owner branch may advance while hashing/logging; never issue a stale BuildID.
$e07HeadAtSeal=((& git -C $e07RepoRoot rev-parse HEAD) | Out-String).Trim().ToLowerInvariant()
if ($LASTEXITCODE -ne 0 -or $e07HeadAtSeal -cne $commit) { throw 'E07_CHECKOUT_SHA_DRIFT_BEFORE_SEAL' }
WriteReceiptNoClobber $Output (($receipt | ConvertTo-Json -Depth 8)+[Environment]::NewLine)
$actual=Get-Content -LiteralPath $Output -Raw -Encoding UTF8 | ConvertFrom-Json
if ($actual.build_id -cne $buildId -or $actual.setup_sha256 -cne $setupSha -or
 $actual.published_exe_sha256 -cne $exeSha -or $actual.release_accepted -ne $false) {
 throw 'E07_HANDOFF_READBACK_DRIFT'
}
if ($Phase -ceq 'INSTALLED') {
 foreach ($name in @('install','launch','update','rollback','uninstall')) {
  $stored=[string]$actual.lifecycle_log_sha256.$name
  if ($stored -cne [string]$logs[$name] -or
      (FileSha ([string]$logPaths[$name])) -cne $stored) {
   throw "E07_LIFECYCLE_LOG_READBACK_DRIFT:$name"
  }
 }
}
Write-Host "E07_BUILDID_SEALED $buildId PHASE=$Phase RELEASE_NOT_ACCEPTED"
