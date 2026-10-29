# P01: verify publisher-provided contents before any activation. Windows PowerShell 5.1-compatible.
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$Root,
  [Parameter(Mandatory=$true)][string]$Manifest,
  [switch]$AllowInstalledMetadata,
  [switch]$ReportVersion
)
$ErrorActionPreference = 'Stop'
function Fail([string]$reason) { throw "P01_PAYLOAD_VERIFY_FAILED: $reason" }
$rootInfo = Get-Item -LiteralPath $Root -ErrorAction Stop
if (-not $rootInfo.PSIsContainer -or (($rootInfo.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) { Fail 'unsafe or reparse root' }
$rootFull = [IO.Path]::GetFullPath($rootInfo.FullName).TrimEnd('\')
function Assert-NoReparseAncestors([string]$Target) {
  $cursor = [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($Target))
  while ($cursor -and ($cursor -ieq $rootFull -or $cursor.StartsWith($rootFull+'\',[StringComparison]::OrdinalIgnoreCase))) {
    $node = Get-Item -LiteralPath $cursor -Force -ErrorAction Stop
    if (-not $node.PSIsContainer -or (($node.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
      Fail "reparse or non-directory ancestor $cursor"
    }
    if ($cursor -ieq $rootFull) { break }
    $cursor = [IO.Path]::GetDirectoryName($cursor)
  }
}
$manifestFull = [IO.Path]::GetFullPath($Manifest)
if ($manifestFull -ine (Join-Path $rootFull 'payload.sha256.json')) { Fail 'noncanonical manifest path' }
Assert-NoReparseAncestors $manifestFull
$manifestItem=Get-Item -LiteralPath $manifestFull -Force -ErrorAction Stop
if ($manifestItem.PSIsContainer -or (($manifestItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) { Fail 'unsafe manifest' }
$m = Get-Content -LiteralPath $manifestFull -Raw -Encoding UTF8 | ConvertFrom-Json
if ($m.schema -cne 'NOX_P01_PAYLOAD_SHA256_V1') { Fail 'schema' }
if ($m.entrypoint -cne 'NOX.P01.Shell.exe') { Fail 'entrypoint' }
if ($null -eq $m.files -or @($m.files).Count -lt 1 -or @($m.files).Count -gt 50000) { Fail 'invalid manifest length' }
if ($m.runId -isnot [string] -or $m.runId -ceq 'P01-UNSET' -or $m.runId -cnotmatch '^[A-Za-z0-9][A-Za-z0-9._:-]{1,127}$') { Fail 'invalid run ID' }
if ($m.version -isnot [string] -or $m.version -cnotmatch '^[0-9]{1,5}\.[0-9]{1,5}\.[0-9]{1,5}(\.[0-9]{1,5})?$') { Fail 'invalid version' }
$registered = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
foreach($f in $m.files) {
  if ($null -eq $f -or $f.path -isnot [string] -or ([string]$f.sha256) -cnotmatch '^[a-fA-F0-9]{64}$') { Fail 'bad manifest row or SHA' }
  $validBytes = [int64]0
  if (-not [int64]::TryParse(([string]$f.bytes),[Globalization.NumberStyles]::None,[Globalization.CultureInfo]::InvariantCulture,[ref]$validBytes)) { Fail 'invalid file length' }
  $rel = [string]$f.path
  # Reject visually equivalent Unicode names before admission or hashing.
  if ($rel -cne $rel.Normalize([Text.NormalizationForm]::FormC)) {
    Fail 'noncanonical Unicode payload path'
  }
  if ([string]::IsNullOrWhiteSpace($rel) -or [IO.Path]::IsPathRooted($rel) -or $rel -match '(^|[\\/])\.\.([\\/]|$)' -or $rel -match '[:*?"<>|]') { Fail "invalid path $rel" }
  $segments=@($rel -split '[\\/]')
  foreach ($part in $segments) {
    if ($part -eq '' -or $part -eq '.' -or $part -eq '..' -or $part -match '[. ]$' -or $part -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$') { Fail 'unsafe Windows component' }
  }
  $rel = $rel.Replace('/','\')
  if ($rel -ieq 'payload.sha256.json' -or $rel -ieq 'nox-p01-owned.txt' -or $rel -ieq 'Uninstall.exe') { Fail 'installer metadata is not application payload' }
  if (-not $registered.Add($rel)) { Fail "duplicate path $rel" }
  $full = [IO.Path]::GetFullPath((Join-Path $rootFull $rel))
  if (-not $full.StartsWith($rootFull+'\',[StringComparison]::OrdinalIgnoreCase)) { Fail "escape $rel" }
  Assert-NoReparseAncestors $full
  $obj = Get-Item -LiteralPath $full -ErrorAction Stop
  if ($obj.PSIsContainer -or (($obj.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) { Fail "not regular file $rel" }
  if ($obj.Length -ne [int64]$f.bytes) { Fail "size mismatch $rel" }
  $actual = (Get-FileHash -LiteralPath $full -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($actual -cne ([string]$f.sha256).ToLowerInvariant()) { Fail "sha mismatch $rel" }
}
# Reject all nested directory reparse points, including empty junctions.
$allDirs = @(Get-ChildItem -LiteralPath $rootFull -Recurse -Force -Directory)
foreach ($dir in $allDirs) {
  if (($dir.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { Fail "reparse directory $($dir.FullName)" }
  Assert-NoReparseAncestors $dir.FullName
}
# Installed backups also contain the installer ownership marker and the
# NSIS-generated uninstaller (not publisher payload). Allow ONLY these exact
# entries for the explicit rollback verifier, not for fresh staging.
$metadata = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
if ($AllowInstalledMetadata) {
  $marker = Join-Path $rootFull 'nox-p01-owned.txt'
  Assert-NoReparseAncestors $marker
  $markerInfo = Get-Item -LiteralPath $marker -Force -ErrorAction Stop
  if ($markerInfo.PSIsContainer -or
      (($markerInfo.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) -or
      $markerInfo.Length -ne 19 -or
      [IO.File]::ReadAllText($marker,[Text.Encoding]::ASCII) -cne
        ('NOXHELION.P01 V16'+[char]13+[char]10)) {
    Fail 'invalid backup ownership marker'
  }
  [void]$metadata.Add('nox-p01-owned.txt')
  $uninstaller = Join-Path $rootFull 'Uninstall.exe'
  Assert-NoReparseAncestors $uninstaller
  $uninstallerInfo = Get-Item -LiteralPath $uninstaller -Force -ErrorAction Stop
  if ($uninstallerInfo.PSIsContainer -or
      (($uninstallerInfo.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) -or
      $uninstallerInfo.Length -lt 1024 -or $uninstallerInfo.Length -gt 104857600) {
    Fail 'invalid generated NSIS metadata'
  }
  # This file is NOT SHA-attested by the payload manifest; rollback does not
  # execute it, and E07 must verify the eventual installed uninstaller.
  [void]$metadata.Add('Uninstall.exe')
}
# Include only regular files the packager approved; prevents hidden extras in staging.
$actualFiles = @(Get-ChildItem -LiteralPath $rootFull -Recurse -Force -File)
foreach ($file in $actualFiles) {
  Assert-NoReparseAncestors $file.FullName
  if (($file.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { Fail "reparse $($file.FullName)" }
  $rel = $file.FullName.Substring($rootFull.Length+1)
  if ($rel -eq 'payload.sha256.json') { continue }
  if (-not $registered.Contains($rel) -and -not $metadata.Contains($rel)) { Fail "unexpected file $rel" }
}
if ($actualFiles.Count -ne ($registered.Count + 1 + $metadata.Count)) { Fail 'file count mismatch' }
if (-not (Test-Path -LiteralPath (Join-Path $rootFull 'NOX.P01.Shell.exe') -PathType Leaf)) { Fail 'entrypoint absent' }
# Rollback registration uses ONLY the existing validated manifest version.
# No newline: nsExec captures exactly this value, not a PASS marker or CR/LF.
if ($ReportVersion) { [Console]::Out.Write([string]$m.version) }
else { 'P01_PAYLOAD_SHA256_PASS' }
