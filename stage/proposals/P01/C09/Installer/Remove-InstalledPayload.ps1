# NOX V16 E01 C09 · fail-closed two-phase uninstall. Windows PowerShell 5.1.
# A compromised/modified payload is NEVER partly removed by preflight.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$InstallRoot)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$expected = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs\NOX HELION')).TrimEnd('\')
$root = [IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')
if ($root -ine $expected) { throw 'P01_UNINSTALL_WRONG_ROOT' }
$localRoot = [IO.Path]::GetFullPath($env:LOCALAPPDATA).TrimEnd('\')
function Assert-DirectoryChain([string]$Path, [string]$StopRoot) {
  $cursor = [IO.Path]::GetFullPath($Path).TrimEnd('\')
  while ($cursor -and ($cursor -ieq $StopRoot -or $cursor.StartsWith($StopRoot+'\',[StringComparison]::OrdinalIgnoreCase))) {
    if (Test-Path -LiteralPath $cursor) {
      $node = Get-Item -LiteralPath $cursor -Force -ErrorAction Stop
      if (-not $node.PSIsContainer -or (($node.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
        throw "P01_UNINSTALL_UNSAFE_PARENT:$cursor"
      }
    }
    if ($cursor -ieq $StopRoot) { break }
    $cursor = [IO.Path]::GetDirectoryName($cursor)
  }
}
Assert-DirectoryChain $root $localRoot
if (-not (Test-Path -LiteralPath $root -PathType Container)) { throw 'P01_UNINSTALL_ROOT_MISSING' }
$markerPath = Join-Path $root 'nox-p01-owned.txt'
$manifestPath = Join-Path $root 'payload.sha256.json'
foreach ($meta in @($markerPath, $manifestPath)) {
  Assert-DirectoryChain ([IO.Path]::GetDirectoryName($meta)) $root
  if (-not (Test-Path -LiteralPath $meta -PathType Leaf)) { throw 'P01_UNINSTALL_METADATA_MISSING' }
  $metaInfo=Get-Item -LiteralPath $meta -Force -ErrorAction Stop
  if (($metaInfo.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'P01_UNINSTALL_METADATA_REPARSE' }
}
$ownership = (Get-Content -LiteralPath $markerPath -Raw -Encoding UTF8).Trim()
if ($ownership -cne 'NOXHELION.P01 V16') { throw 'P01_UNINSTALL_INVALID_OWNER_MARKER' }
# Reject duplicate JSON member names before ConvertFrom-Json may collapse them.
# Published payload manifest member names are fixed unescaped ASCII.
function Assert-NoDuplicateJsonMembers([string]$Text) {
  $frames = New-Object 'System.Collections.Generic.List[object]'
  for ($i = 0; $i -lt $Text.Length; $i++) {
    $ch = $Text[$i]
    if ($ch -eq [char]34) {
      $start = $i + 1
      $escaped = $false
      for ($i = $i + 1; $i -lt $Text.Length; $i++) {
        if ($Text[$i] -eq [char]92) { $escaped = $true; $i++; continue }
        if ($Text[$i] -eq [char]34) { break }
      }
      if ($i -ge $Text.Length) { throw 'P01_JSON_UNTERMINATED_STRING' }
      if ($frames.Count -gt 0) {
        $top = $frames[$frames.Count - 1]
        if ($top.Kind -eq 'object' -and $top.ExpectKey) {
          if ($escaped) { throw 'P01_JSON_ESCAPED_MEMBER_NAME' }
          $key = $Text.Substring($start, $i - $start)
          if (-not $top.Keys.Add($key)) { throw 'P01_JSON_DUPLICATE_MEMBER' }
          $top.ExpectKey = $false
        }
      }
      continue
    }
    switch ([int]$ch) {
      123 {
        $keys = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
        $frames.Add([pscustomobject]@{ Kind='object'; Keys=$keys; ExpectKey=$true })
      }
      91 { $frames.Add([pscustomobject]@{ Kind='array' }) }
      125 { if ($frames.Count -gt 0) { $frames.RemoveAt($frames.Count - 1) } }
      93 { if ($frames.Count -gt 0) { $frames.RemoveAt($frames.Count - 1) } }
      44 {
        if ($frames.Count -gt 0) {
          $top = $frames[$frames.Count - 1]
          if ($top.Kind -eq 'object') { $top.ExpectKey = $true }
        }
      }
    }
  }
}
$manifestRaw = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8
Assert-NoDuplicateJsonMembers $manifestRaw
$m = $manifestRaw | ConvertFrom-Json -ErrorAction Stop
if ($m.schema -cne 'NOX_P01_PAYLOAD_SHA256_V1' -or $m.entrypoint -cne 'NOX.P01.Shell.exe') { throw 'P01_UNINSTALL_BAD_MANIFEST' }
if ($null -eq $m.files -or @($m.files).Count -lt 1 -or @($m.files).Count -gt 50000) { throw 'P01_UNINSTALL_INVALID_MANIFEST_LENGTH' }
if ($m.runId -isnot [string] -or $m.runId -ceq 'P01-UNSET' -or $m.runId -cnotmatch '^[A-Za-z0-9][A-Za-z0-9._:-]{1,127}$') { throw 'P01_UNINSTALL_INVALID_RUN_ID' }
$registered = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
$directories = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
$checked = New-Object 'System.Collections.Generic.List[object]'
$verified = New-Object 'System.Collections.Generic.List[string]'
function Normalize-Relative([string]$Value) {
  if ([string]::IsNullOrWhiteSpace($Value) -or [IO.Path]::IsPathRooted($Value) -or $Value -match '[<>:"|?*]' -or $Value -match '[\x00-\x1f]') { throw 'P01_UNINSTALL_BAD_PATH' }
  $segments = @($Value -split '[\\/]')
  foreach ($part in $segments) {
    if ($part -eq '' -or $part -eq '.' -or $part -eq '..' -or $part -match '[. ]$' -or $part -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$') {
      throw 'P01_UNINSTALL_BAD_PATH'
    }
  }
  return ($segments -join '\')
}
function Assert-VerifiedEntry([object]$Entry) {
  Assert-DirectoryChain ([IO.Path]::GetDirectoryName($Entry.Full)) $root
  if (-not (Test-Path -LiteralPath $Entry.Full -PathType Leaf)) { throw "P01_UNINSTALL_MISSING_PAYLOAD:$($Entry.Relative)" }
  $item = Get-Item -LiteralPath $Entry.Full -Force -ErrorAction Stop
  if ($item.PSIsContainer -or (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) { throw "P01_UNINSTALL_UNSAFE_FILE:$($Entry.Relative)" }
  if ($item.Length -ne $Entry.Size) { throw "P01_UNINSTALL_MODIFIED_FILE:$($Entry.Relative)" }
  $actual = (Get-FileHash -LiteralPath $Entry.Full -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($actual -cne $Entry.Digest) { throw "P01_UNINSTALL_MODIFIED_FILE:$($Entry.Relative)" }
}
# PHASE 1 — validate ALL manifest rows and ALL live files before removing ANYTHING.
foreach ($f in @($m.files)) {
  if ($null -eq $f -or $f.path -isnot [string]) { throw 'P01_UNINSTALL_BAD_ROW' }
  $relative = Normalize-Relative ([string]$f.path)
  if ($relative -ieq 'payload.sha256.json' -or $relative -ieq 'nox-p01-owned.txt' -or $relative -ieq 'Uninstall.exe') { throw 'P01_UNINSTALL_RESERVED_INSTALLER_METADATA' }
  if (-not $registered.Add($relative)) { throw 'P01_UNINSTALL_DUPLICATE_PATH' }
  $full = [IO.Path]::GetFullPath((Join-Path $root $relative))
  if (-not $full.StartsWith($root+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'P01_UNINSTALL_PATH_ESCAPE' }
  $digest = [string]$f.sha256
  $sizeText = [string]$f.bytes
  $size = [int64]0
  if ($digest -cnotmatch '^[a-fA-F0-9]{64}$' -or -not [int64]::TryParse($sizeText,[Globalization.NumberStyles]::None,[Globalization.CultureInfo]::InvariantCulture,[ref]$size)) {
    throw 'P01_UNINSTALL_INVALID_HASH_OR_LENGTH'
  }
  if ($size -lt 0) { throw 'P01_UNINSTALL_INVALID_HASH_OR_LENGTH' }
  $entry = [pscustomobject]@{Relative=$relative;Full=$full;Size=$size;Digest=$digest.ToLowerInvariant()}
  Assert-VerifiedEntry $entry
  [void]$checked.Add($entry)
  [void]$verified.Add($entry.Full)
  $parent = [IO.Path]::GetDirectoryName($full)
  while ($parent -and $parent.Length -gt $root.Length -and $parent.StartsWith($root+'\',[StringComparison]::OrdinalIgnoreCase)) {
    [void]$directories.Add($parent)
    $parent=[IO.Path]::GetDirectoryName($parent)
  }
}
if ($checked.Count -ne $registered.Count -or $checked.Count -lt 1) { throw 'P01_UNINSTALL_REFUSED_MODIFIED_FILES:incomplete-validation' }
# PHASE 2 — full-list drift check BEFORE the first delete, for C08 no-loss parity.
foreach ($entry in $checked) {
  try { Assert-VerifiedEntry $entry } catch { throw "P01_UNINSTALL_FILE_CHANGED_DURING_COMMIT:$($entry.Relative)" }
}
# PHASE 3 — delete ONLY prevalidated payload paths, keep unknown/user data/metadata.
$removed=0
foreach ($entry in $checked) {
  # C11: enforce final per-file digest check just before removal.
  Assert-VerifiedEntry $entry
  Remove-Item -LiteralPath $entry.Full -Force -ErrorAction Stop
  $removed++
}
foreach ($dir in @($directories | Sort-Object Length -Descending)) {
  try { if ((Get-ChildItem -LiteralPath $dir -Force -ErrorAction Stop | Measure-Object).Count -eq 0) { Remove-Item -LiteralPath $dir -Force } } catch { }
}
# NSIS owns metadata + uninstaller cleanup ONLY after this script reports PASS.
Write-Output "P01_UNINSTALL_PAYLOAD_PASS verified=$($checked.Count) removed=$removed"
