# NOX V16 T11 - proposed pinned SourceLock gate (NOT wired into CI)
# This file is source-only: its presence cannot launch a GitLab pipeline.
[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
function Required([string]$name) {
  $value = [Environment]::GetEnvironmentVariable($name)
  if ([string]::IsNullOrWhiteSpace($value)) { throw "NOX_T11_REQUIRED_VAR_MISSING:$name" }
  return $value
}
$source = Required 'CI_PIPELINE_SOURCE'
$consent = Required 'NOX_APPROVE_WINDOWS_BUILD'
$ref = Required 'NOX_FROZEN_REF'
$sha = Required 'NOX_FROZEN_SOURCE_SHA'
$manifestRel = Required 'NOX_FROZEN_MANIFEST_PATH'
$manifestHash = Required 'NOX_FROZEN_MANIFEST_SHA256'
$ciSha = Required 'CI_COMMIT_SHA'
$ciRef = Required 'CI_COMMIT_REF_NAME'
$root = Required 'CI_PROJECT_DIR'
if ($source -cnotin @('web','api') -or $consent -cne 'YES') {
  throw 'NOX_T11_MANUAL_CONSENT_DENIED'
}
if ($sha -cnotmatch '^[a-f0-9]{40}$' -or $ciSha -cnotmatch '^[a-f0-9]{40}$' -or
    $sha -cne $ciSha) { throw 'NOX_T11_FROZEN_SHA_MISMATCH' }
if ($ref -cne $ciRef -or $ref -cnotmatch '^[a-zA-Z0-9._/-]{1,200}$' -or
    $ref.StartsWith('/') -or $ref.Contains('..') -or $ref.Contains('//')) {
  throw 'NOX_T11_FROZEN_REF_MISMATCH'
}
if ($manifestHash -cnotmatch '^[a-f0-9]{64}$') {
  throw 'NOX_T11_FROZEN_MANIFEST_DIGEST_INVALID'
}
if ($manifestRel -cmatch '(^[\\/]|^[a-zA-Z]:|(^|[\\/])\.\.([\\/]|$))' -or
    $manifestRel -cnotmatch '^[a-zA-Z0-9._/\\-]{1,256}$') {
  throw 'NOX_T11_UNSAFE_MANIFEST_PATH'
}
$fullRoot = [IO.Path]::GetFullPath($root)
if (-not (Test-Path -LiteralPath $fullRoot -PathType Container)) {
  throw 'NOX_T11_CHECKOUT_ROOT_MISSING'
}
$manifestPath = [IO.Path]::GetFullPath((Join-Path $fullRoot $manifestRel))
if (-not $manifestPath.StartsWith($fullRoot.TrimEnd('\','/')+[IO.Path]::DirectorySeparatorChar,
         [StringComparison]::OrdinalIgnoreCase)) {
  throw 'NOX_T11_MANIFEST_OUTSIDE_CHECKOUT'
}
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
  throw 'NOX_T11_SOURCELOCK_MANIFEST_MISSING'
}
$actualDigest = (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualDigest -cne $manifestHash) { throw 'NOX_T11_SOURCELOCK_DIGEST_DRIFT' }
$actualHead = (& git -C $fullRoot rev-parse HEAD | Out-String).Trim().ToLowerInvariant()
if ($LASTEXITCODE -ne 0 -or $actualHead -cne $sha) {
  throw 'NOX_T11_GIT_HEAD_DRIFT'
}
# T09/T10 provenance must be verified independently BEFORE approving the environment variables.
# This guard checks only the immutable pinned byte and Git identities, not product SOURCE_READY.
Write-Host 'NOX_T11_PINNED_SOURCE_GUARD_PASS_NOT_BUILD_OR_E07'
