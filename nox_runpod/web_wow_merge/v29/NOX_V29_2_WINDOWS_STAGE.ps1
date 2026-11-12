#requires -Version 5.1
<#
NOX HELION WEB V29.2. Actual source archive verification and isolated staging.
DOES NOT install over live C:\NOX, restart OneHost/Ollama, edit S03, or touch GPU.
Full Windows E07 and explicit owner source promotion remain separate.
#>
[CmdletBinding()]
param(
  [string]$Root = 'C:\NOX',
  [string]$Archive = 'C:\NOX\incoming\NOX_HELION_WEB_V29_2_REAL_PC_API_ROUTES_20261113.zip',
  [switch]$InspectOnly
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ExpectedSha = '3379770d33d56e501d267c2ca603d58bce0e301b2582b6585c1944d5f5ec57d0'
$OriginalD02Sha = 'f3fc804d238146ffe42c50103d3e04c9736b8b587c6572987f59b61a6112eb17'
$ExpectedEntries = 1089
$ExpectedManifest = 1085

function Hex-Sha256Stream($stream) {
  $algo = [System.Security.Cryptography.SHA256]::Create()
  try { return ([BitConverter]::ToString($algo.ComputeHash($stream))).Replace('-','').ToLowerInvariant() }
  finally { $algo.Dispose() }
}
function Read-ZipUtf8($entry) {
  $reader = [System.IO.StreamReader]::new($entry.Open(), [System.Text.Encoding]::UTF8)
  try { return $reader.ReadToEnd() } finally { $reader.Dispose() }
}
function Assert-SafeZipName([string]$name) {
  if ([string]::IsNullOrWhiteSpace($name) -or $name.StartsWith('/') -or
      $name.Contains('\') -or $name.Contains(':') -or $name.Contains([char]0) -or
      -not $name.StartsWith('site/',[StringComparison]::Ordinal)) {
    throw "NOX_UNSAFE_ENTRY: $name"
  }
  $parts=$name.Split('/')
  foreach ($part in $parts) {
    if ($part -eq '' -or $part -eq '.' -or $part -eq '..' -or
        $part.EndsWith(' ') -or $part.EndsWith('.') -or
        $part.Split('.')[0] -match '^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$') {
      throw "NOX_UNSAFE_WINDOWS_PATH: $name"
    }
  }
}
function Get-LocalPCStatus {
  $out = [ordered]@{ status='HOLD'; host='NOT_REACHABLE'; memory='NOT_TESTED'; dialogs='NOT_TESTED' }
  try {
    $status = Invoke-RestMethod -Uri 'http://127.0.0.1:8766/api/nox/status' -TimeoutSec 5 -Method Get
    if (($status.host -ne 'NOX_CHAT_V24.1') -and
        -not ($status.backend -eq 'EXISTING_NATIVE_ONEHOST' -and $status.native_p02_bound -eq $true)) {
      $out.status='HOLD_UNRECOGNIZED_PC_SERVER'
      return $out
    }
    $out.host=[string]($status.host)
    $out.status='READ_ONLY_PC_STATUS_VERIFIED'
    $memory=Invoke-RestMethod -Uri 'http://127.0.0.1:8766/api/nox/memory' -TimeoutSec 5 -Method Get
    if ($memory.status -eq 'READY' -and $null -ne $memory.segments -and $null -ne $memory.stats) {
      $out.memory='S03_API_READ_OK_NOT_RESTART_TESTED'
    } else { $out.memory='HOLD_SCHEMA_MISMATCH' }
    $hist=Invoke-RestMethod -Uri 'http://127.0.0.1:8766/api/nox/history' -TimeoutSec 5 -Method Get
    if ($hist.status -eq 'READY' -and $null -ne $hist.dialogs) {
      $out.dialogs='HISTORY_API_READ_OK_NOT_RESTART_TESTED'
    } else { $out.dialogs='HOLD_SCHEMA_MISMATCH' }
  }
  catch {
    $out.status='HOLD_PC_API_UNAVAILABLE'
    $out.reason=$_.Exception.GetType().Name
  }
  return $out
}
if (-not (Test-Path -LiteralPath $Archive -PathType Leaf)) {
  throw "NOX_ARCHIVE_MISSING: $Archive"
}
$ActualSha=(Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ActualSha -cne $ExpectedSha) {
  throw "NOX_ARCHIVE_SOURCELOCK_HOLD: expected $ExpectedSha actual $ActualSha"
}
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip=[System.IO.Compression.ZipFile]::OpenRead($Archive)
try {
  $files=@{}
  foreach ($entry in $zip.Entries) {
    if ($entry.FullName.EndsWith('/')) { continue }
    Assert-SafeZipName $entry.FullName
    if ($files.ContainsKey($entry.FullName)) { throw "NOX_CASE_COLLISION: $($entry.FullName)" }
    $unixMode=([int]($entry.ExternalAttributes -shr 16)) -band 0xF000
    if ($unixMode -eq 0xA000) { throw "NOX_SYMLINK_ENTRY_HOLD: $($entry.FullName)" }
    $files[$entry.FullName]=$entry
  }
  if ($files.Count -ne $ExpectedEntries) {
    throw "NOX_V29_2_MEMBER_COUNT_HOLD: $($files.Count)"
  }
  foreach ($required in @('site/SOURCE_MANIFEST_V29.json',
      'site/NOX_V29_UNIFIED_RECEIPT.json','site/index.html','site/chat.html',
      'site/memory.html','site/resonance.html','site/nox-v29-pc-genesis-addons.mjs',
      'site/nox-v29-pc-genesis-addons.css','site/pc/resonance.html',
      'site/pc/memory.html','site/qa/v29/test_v29_static_routes.py')) {
    if (-not $files.ContainsKey($required)) { throw "NOX_REQUIRED_SOURCE_MISSING: $required" }
  }
  $meta=Read-ZipUtf8 $files['site/NOX_V29_UNIFIED_RECEIPT.json'] | ConvertFrom-Json
  if ($meta.schema -ne 'NOX_HELION_WEB_V29_ONEPASS_SIX_TASKS_SOURCE_RECEIPT_V1' -or
      $meta.production_modified -ne $false -or $meta.release_accepted -ne $false) {
    throw 'NOX_UNTRUSTED_SOURCE_OR_FALSE_RELEASE_RECEIPT'
  }
  $manifest=Read-ZipUtf8 $files['site/SOURCE_MANIFEST_V29.json'] | ConvertFrom-Json
  $props=@($manifest.PSObject.Properties)
  if ($props.Count -ne $ExpectedManifest) {
    throw "NOX_SOURCE_MANIFEST_COUNT_HOLD: $($props.Count)"
  }
  foreach ($prop in $props) {
    $name='site/'+$prop.Name
    if (-not $files.ContainsKey($name)) { throw "NOX_LOCK_ENTRY_MISSING: $name" }
    $entry=$files[$name]
    if ($entry.Length -ne [long]$prop.Value.bytes) {
      throw "NOX_SIZE_DRIFT_HOLD: $name"
    }
    $stream=$entry.Open()
    try { $got=Hex-Sha256Stream $stream } finally { $stream.Dispose() }
    if ($got -cne [string]$prop.Value.sha256) {
      throw "NOX_SHA_DRIFT_HOLD: $name"
    }
  }
  $d02=$files['site/index.html'].Open()
  try { $d02hash=Hex-Sha256Stream $d02 } finally { $d02.Dispose() }
  if ($d02hash -cne $OriginalD02Sha) { throw 'NOX_D02_SOURCE_HASH_HOLD' }
  $local=Get-LocalPCStatus
  if ($InspectOnly) {
    Write-Output "NOX_V29_2_ARCHIVE_FULL_SHA_PASS: $ActualSha"
    Write-Output "NOX_V29_2_LOCKED_FILES_PASS: $($props.Count)"
    Write-Output "NOX_PC_STATUS: $($local.status); S03=$($local.memory); HISTORY=$($local.dialogs)"
    Write-Output 'NOX_WINDOWS_WEBVIEW2_E07_HOLD; no source applied.'
    exit 0
  }
  $builds=Join-Path $Root 'builds'
  $stage=Join-Path $builds 'NOX_WEB_V29_2_VERIFIED_STAGE_3379770d33d5'
  if (Test-Path -LiteralPath $stage) {
    throw "NOX_STAGE_ALREADY_EXISTS_NO_OVERWRITE: $stage"
  }
  if (-not (Test-Path -LiteralPath $builds -PathType Container)) {
    [void](New-Item -ItemType Directory -Path $builds -Force)
  }
  [void](New-Item -ItemType Directory -Path $stage)
  try {
    $stageRoot=[System.IO.Path]::GetFullPath($stage).TrimEnd('\','/')
    foreach ($entry in $files.Values) {
      $rel=$entry.FullName.Substring(5).Replace('/',[System.IO.Path]::DirectorySeparatorChar)
      $target=[System.IO.Path]::GetFullPath((Join-Path $stage $rel))
      if (-not $target.StartsWith($stageRoot+[System.IO.Path]::DirectorySeparatorChar,
                                   [StringComparison]::OrdinalIgnoreCase)) {
        throw "NOX_EXTRACT_OUTSIDE_STAGE_HOLD: $rel"
      }
      $dir=[System.IO.Path]::GetDirectoryName($target)
      if (-not (Test-Path -LiteralPath $dir -PathType Container)) {
        [void](New-Item -ItemType Directory -Path $dir -Force)
      }
      [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry,$target)
    }
    $actual=(Get-FileHash -LiteralPath (Join-Path $stage 'index.html') -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -cne $OriginalD02Sha) { throw 'NOX_STAGED_D02_MISMATCH' }
    $receipt=[ordered]@{
      schema='NOX-V29_2-WINDOWS-SOURCE-STAGE-v1'
      utc=(Get-Date).ToUniversalTime().ToString('o')
      zip_sha256=$ActualSha
      manifest_verified_sha256_count=$props.Count
      files_staged=$files.Count
      stage=$stage
      pc_api=$local
      production_modified=$false
      s03_restart_tested=$false
      gpu_safe70_tested=$false
      e07_verified=$false
      release_accepted=$false
    }
    $receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $stage 'NOX_V29_2_WINDOWS_STAGE_RECEIPT.json') -Encoding UTF8
    Write-Output "NOX_V29_2_WINDOWS_SOURCE_STAGE_PASS: $stage"
    Write-Output "NOX_V29_2_1085_LOCKED_SHA_PASS"
    Write-Output "NOX_PC_STATUS: $($local.status); S03=$($local.memory); HISTORY=$($local.dialogs)"
    Write-Output 'NOX_NATIVE_WEBVIEW2_STOP_VOICE_GPU_E07_HOLD; original PC site and models remain untouched.'
  }
  catch {
    # Only this newly created isolated stage can be cleaned on failure.
    if (Test-Path -LiteralPath $stage) {
      Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
    }
    throw
  }
}
finally { $zip.Dispose() }
