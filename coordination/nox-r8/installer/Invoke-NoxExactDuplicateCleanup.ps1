# NOX R8: exact-byte duplicate removal only; never infer "obsolete" from names or dates.
# instructions_version: 0.0.6; NO-LOSS. Does not install, download, modify weights or merge models.
[CmdletBinding()]
param(
  [Parameter(Mandatory)][string]$Root,
  [Parameter(Mandatory)][string]$CanonicalFile,
  [Parameter(Mandatory)][ValidatePattern('^[0-9a-fA-F]{64}$')][string]$CanonicalSha256,
  [switch]$Apply
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$base = (Resolve-Path -LiteralPath $Root -ErrorAction Stop).Path.TrimEnd('\','/')
$canonical = (Resolve-Path -LiteralPath $CanonicalFile -ErrorAction Stop).Path
if (!(Test-Path -LiteralPath $canonical -PathType Leaf)) { throw 'NOX_CANONICAL_FILE_MISSING' }
if ($base -match '(?i)[\\/](models|weights|sqlite|memory|rag|checkpoints|training|datasets|\.git)([\\/]|$)') {
  throw 'NOX_PROTECTED_ROOT'
}
$actual = (Get-FileHash -LiteralPath $canonical -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -cne $CanonicalSha256.ToLowerInvariant()) { throw 'NOX_CANONICAL_HASH_HOLD' }
$canonicalInfo = Get-Item -LiteralPath $canonical -Force
if ($canonicalInfo.Attributes.HasFlag([IO.FileAttributes]::ReparsePoint)) { throw 'NOX_CANONICAL_LINK_HOLD' }
# Cleanup is strictly confined to distributable containers and matching extension.
$allowed = @('.exe','.zip','.7z','.msi')
$extension = $canonicalInfo.Extension.ToLowerInvariant()
if ($extension -notin $allowed) { throw 'NOX_UNSUPPORTED_CLEANUP_EXTENSION' }
$rootsafe = $base + [IO.Path]::DirectorySeparatorChar
if (!$canonical.StartsWith($rootsafe,[StringComparison]::OrdinalIgnoreCase)) {
  throw 'NOX_CANONICAL_OUTSIDE_ROOT'
}
$protected = '(?i)(^|[\\/])(models|weights|memory|sqlite|checkpoints|datasets|training|\.git|90_АРХИВ_ПРОЕКТА)([\\/]|$)'
$matches = [System.Collections.Generic.List[string]]::new()
$skipped = 0
foreach($f in Get-ChildItem -LiteralPath $base -File -Recurse -Force -ErrorAction Stop) {
  if ($f.FullName -eq $canonical) { continue }
  if ($f.FullName -match $protected -or $f.Attributes.HasFlag([IO.FileAttributes]::ReparsePoint)) { $skipped++; continue }
  if ($f.Extension.ToLowerInvariant() -ne $extension -or $f.Length -ne $canonicalInfo.Length) { continue }
  $hash=(Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($hash -ceq $actual) { $matches.Add($f.FullName) }
}
$deleted = 0
if ($Apply) {
  foreach($file in $matches) {
    # Revalidate BOTH files just before deletion; no "old but different" purges.
    if ((Get-FileHash -LiteralPath $canonical -Algorithm SHA256).Hash.ToLowerInvariant() -cne $actual) { throw 'NOX_CANONICAL_CHANGED_HOLD' }
    if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -cne $actual) { throw 'NOX_DUPLICATE_CHANGED_HOLD' }
    Remove-Item -LiteralPath $file -Force -ErrorAction Stop
    if (Test-Path -LiteralPath $file) { throw 'NOX_CLEANUP_DELETE_UNVERIFIED' }
    $deleted++
  }
}
[ordered]@{
  schema = 'NOX_EXACT_DUPLICATE_CLEANUP_V1'
  canonical = $canonical
  canonical_sha256 = $actual
  root = $base
  mode = $(if ($Apply) {'APPLY'} else {'DRY_RUN'})
  matched_exact_duplicates = $matches.Count
  deleted = $deleted
  protected_skipped = $skipped
  duplicate_paths = @($matches.ToArray())
  unique_versions_removed = 0
  conclusion = 'EXACT_BYTES_ONLY'
} | ConvertTo-Json -Depth 5
