#requires -Version 5.1
<#
NOX HELION WEB WOW V27 — native Windows preflight + optional reversible promotion.
DEFAULT: safe, creates ONLY a unique staging directory and writes a verification report.
-Apply: explicit approval + exact SHA + explicit existing LiveWeb path.
NO autonomous Windows installs, new backends, model deletions, GPU training or S03 changes.
#>
[CmdletBinding()]
param(
    [string]$Root = 'C:\NOX',
    [string]$Archive = 'C:\NOX\incoming\NOX_HELION_WEB_WOW_V27_UNIFIED_SOURCE_20261113.zip',
    [string]$LiveWeb = '',
    [switch]$Apply,
    [string]$ApproveSha256 = ''
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Require-Http200([string]$Url) {
    $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 8 -MaximumRedirection 3
    if ([int]$r.StatusCode -ne 200) { throw "NOX_HTTP_NOT_200 $Url $($r.StatusCode)" }
}
function Require-ExistingJsonApi([string]$Url, [string]$Kind) {
    $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 8 -MaximumRedirection 0
    if ([int]$r.StatusCode -ne 200) { throw "NOX_API_HTTP_HOLD $Url" }
    try { $data = $r.Content | ConvertFrom-Json }
    catch { throw "NOX_API_NOT_JSON_HOLD $Kind" }
    if ($data.status -notin @('READY', 'HOLD')) {
        throw "NOX_API_STATUS_SCHEMA_HOLD $Kind"
    }
    if ($Kind -eq 'status' -and -not $data.PSObject.Properties['self_core']) {
        throw 'NOX_API_NOT_AUTHENTICATED_EXISTING_HOST'
    }
    if ($Kind -eq 'memory' -and (-not $data.PSObject.Properties['segments'] -or
                                 -not $data.PSObject.Properties['levels'])) {
        throw 'NOX_MEMORY_NOT_ORIGINAL_S03_SCHEMA'
    }
    if ($data.status -eq 'HOLD') { throw "NOX_EXISTING_API_HOLD $Kind" }
    return $data
}
function Require-ContainedDirectory([string]$Path, [string]$Base) {
    $full = [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
    $baseFull = [System.IO.Path]::GetFullPath($Base).TrimEnd('\')
    if (-not $full.StartsWith(($baseFull + '\'), [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'NOX_DIRECTORY_OUTSIDE_APPROVED_ROOT'
    }
    if (-not (Test-Path -LiteralPath $full -PathType Container)) {
        throw "NOX_LIVE_WEB_PATH_NOT_FOUND $full"
    }
    $attr = (Get-Item -LiteralPath $full).Attributes
    if ($attr -band [System.IO.FileAttributes]::ReparsePoint) {
        throw 'NOX_SYMLINK_OR_JUNCTION_LIVE_WEB_HOLD'
    }
    return $full
}
if (-not (Test-Path -LiteralPath $Archive -PathType Leaf)) {
    throw "NOX_ARCHIVE_MISSING $Archive"
}
if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
    throw "NOX_ROOT_MISSING $Root"
}
$ArchiveSha = (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($Apply) {
    if ($ApproveSha256 -ne $ArchiveSha) {
        throw 'NOX_OWNER_EXACT_ARCHIVE_SHA_APPROVAL_REQUIRED'
    }
    if ([string]::IsNullOrWhiteSpace($LiveWeb)) {
        throw 'NOX_LIVE_WEB_EXACT_PATH_REQUIRED_FOR_APPLY'
    }
}
$Builds = Join-Path $Root 'builds'
if (-not (Test-Path -LiteralPath $Builds)) { New-Item -ItemType Directory -Path $Builds -Force | Out-Null }
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ')
$Stage = Join-Path $Builds ('NOX_WEB_WOW_V27_STAGE_' + $stamp)
if (Test-Path -LiteralPath $Stage) { throw 'NOX_STAGING_COLLISION' }
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zipObj = [System.IO.Compression.ZipFile]::OpenRead($Archive)
try {
    $names = New-Object 'System.Collections.Generic.HashSet[string]' ([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($entry in $zipObj.Entries) {
        $name = [string]$entry.FullName
        if ($name.StartsWith('/') -or $name.Contains('\') -or $name.Contains(':') -or
            $name.Contains([char]0) -or $name -match '(^|/)\.\.?(/|$)') {
            throw "NOX_ARCHIVE_UNSAFE_ENTRY $name"
        }
        if (-not $names.Add($name)) { throw "NOX_ARCHIVE_CASE_COLLISION $name" }
    }
} finally { $zipObj.Dispose() }
Expand-Archive -LiteralPath $Archive -DestinationPath $Stage -ErrorAction Stop
$Site = Join-Path $Stage 'site'
$Lock = Join-Path $Stage 'NOX_V27_SOURCE_LOCK.json'
$Receipt = Join-Path $Stage 'NOX_V27_BUILD_RECEIPT.json'
if (-not (Test-Path -LiteralPath $Site -PathType Container) -or
    -not (Test-Path -LiteralPath $Lock -PathType Leaf) -or
    -not (Test-Path -LiteralPath $Receipt -PathType Leaf)) {
    throw 'NOX_MISSING_SITE_OR_SOURCELOCK_OR_RECEIPT'
}
$R = Get-Content -LiteralPath $Receipt -Raw -Encoding UTF8 | ConvertFrom-Json
if ($R.release_accepted -ne $false -or $R.production_modified -ne $false -or
    $R.schema -ne 'NOX-WEB-WOW-V27-UNIFIED-SOURCE-CANDIDATE-v1') {
    throw 'NOX_UNTRUSTED_SOURCE_RECEIPT'
}
$S = Get-Content -LiteralPath $Lock -Raw -Encoding UTF8 | ConvertFrom-Json
if ($S.schema -ne 'NOX-UNIFIED-WEB-SOURCE-LOCK-v27') {
    throw 'NOX_UNEXPECTED_SOURCE_LOCK_SCHEMA'
}
$count = 0
foreach ($property in $S.site.PSObject.Properties) {
    $name = [string]$property.Name
    if ($name.Contains('..') -or $name.StartsWith('/') -or $name.Contains(':') -or $name.Contains('\')) {
        throw 'NOX_SOURCELOCK_UNSAFE_PATH'
    }
    $path = Join-Path $Site ($name.Replace('/', '\'))
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "NOX_SOURCE_MISSING $name" }
    $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne [string]$property.Value) { throw "NOX_SOURCE_HASH_MISMATCH $name" }
    $count++
}
if ($count -ne 1046) { throw "NOX_SOURCELOCK_FILE_COUNT_MISMATCH $count" }
$D02 = (Get-FileHash -LiteralPath (Join-Path $Site 'index.html') -Algorithm SHA256).Hash.ToLowerInvariant()
if ($D02 -ne $R.original_d02_sha256 -or $D02 -ne $R.merged_d02_sha256) {
    throw 'NOX_ORIGINAL_D02_TAMPER_HOLD'
}
foreach ($path in @('chat.html','memory.html','training.html','cinema.html',
                    'pc\resonance.html','pc\memory.html','pc\v25\nox-shell-v25.js',
                    'pc\vendor\fonts\tektur\tektur.css')) {
    if (-not (Test-Path -LiteralPath (Join-Path $Site $path) -PathType Leaf)) {
        throw "NOX_REQUIRED_COMPONENT_NOT_FOUND $path"
    }
}
# Read-only checks of the *existing* service; do not start or stop it.
$liveStatus = Require-ExistingJsonApi 'http://127.0.0.1:8766/api/nox/status' 'status'
$liveMemory = Require-ExistingJsonApi 'http://127.0.0.1:8766/api/nox/memory' 'memory'
$pre = [ordered]@{event='NOX_V27_WINDOWS_STATIC_PREFLIGHT';time_utc=(Get-Date).ToUniversalTime().ToString('o');
  archive_sha256=$ArchiveSha;source_sha_files=$count;d02_sha256=$D02;
  chat_status_http200=$true;memory_http200=$true;
  onehost_ollama_streaming='NOT_TESTED';s03_restart='NOT_TESTED';gpu='NOT_TOUCHED';
  windows_e07='NOT_TESTED';production_modified=$false;owner_apply_requested=[bool]$Apply}
$pre | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $Stage 'NOX_WINDOWS_PREFLIGHT.json') -Encoding UTF8
if (-not $Apply) {
    Write-Output "NOX_V27_PREFLIGHT_PASS: 1046 file hashes, original D02, status and memory readbacks."
    Write-Output "STAGING: $Stage"
    Write-Output "ZIP_SHA256: $ArchiveSha"
    Write-Output 'NO LIVE MODIFICATION. E07/STOP/GPU/VOICE STILL HOLD.'
    exit 0
}
$Live = Require-ContainedDirectory $LiveWeb $Root
$OriginalIndex = Join-Path $Live 'index.html'
if (-not (Test-Path -LiteralPath $OriginalIndex -PathType Leaf)) {
    throw 'NOX_EXISTING_LIVE_HOME_MISSING'
}
$OriginalD02 = (Get-FileHash -LiteralPath $OriginalIndex -Algorithm SHA256).Hash.ToLowerInvariant()
$ArchiveDir = Join-Path $Root 'archive'
if (-not (Test-Path -LiteralPath $ArchiveDir)) {
    New-Item -ItemType Directory -Path $ArchiveDir -Force | Out-Null
}
$Backup = Join-Path $ArchiveDir ('NOX_WEB_BEFORE_V27_' + $stamp)
if (Test-Path -LiteralPath $Backup) { throw 'NOX_BACKUP_COLLISION' }
$MovedOld = $false
$MovedNew = $false
try {
    # Brief static-route interruption may occur. This is NOT zero-downtime acceptance.
    Move-Item -LiteralPath $Live -Destination $Backup -ErrorAction Stop
    $MovedOld = $true
    Move-Item -LiteralPath $Site -Destination $Live -ErrorAction Stop
    $MovedNew = $true
    foreach ($route in @('/index.html','/chat.html','/memory.html','/training.html',
                         '/pc/resonance.html','/pc/memory.html','/pc/v25/nox-shell-v25.js')) {
        Require-Http200 ('http://127.0.0.1:8766' + $route)
    }
    Require-Http200 'http://127.0.0.1:8766/api/nox/status'
    Require-Http200 'http://127.0.0.1:8766/api/nox/memory'
    if ((Get-FileHash -LiteralPath (Join-Path $Live 'index.html') -Algorithm SHA256).Hash.ToLowerInvariant() -ne $D02) {
        throw 'NOX_POST_PROMOTION_D02_DRIFT'
    }
    $post = [ordered]@{event='NOX_V27_SOURCE_PROMOTED_SAME_HOST';time_utc=(Get-Date).ToUniversalTime().ToString('o');
      archive_sha256=$ArchiveSha;backup=$Backup;previous_index_sha256=$OriginalD02;
      current_index_sha256=$D02;health_http200=$true;memory_http200=$true;
      owner_apply_approved=$true;gpu_modified=$false;s03_modified=$false;
      windows_e07='HOLD';release_accepted=$false}
    $post | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath (Join-Path $Stage 'NOX_WINDOWS_PROMOTION.json') -Encoding UTF8
    Write-Output "NOX_V27_STATIC_PROMOTION_HTTP_PASS; backup: $Backup"
    Write-Output 'RELEASE STILL HOLD: independent E07/STOP/streaming/voice/GPU required.'
} catch {
    $errorText = $_.Exception.Message
    if ($MovedNew -and (Test-Path -LiteralPath $Live)) {
        $Rejected = Join-Path $Builds ('NOX_WEB_V27_REJECTED_' + $stamp)
        Move-Item -LiteralPath $Live -Destination $Rejected -ErrorAction Stop
    }
    if ($MovedOld -and (Test-Path -LiteralPath $Backup) -and -not (Test-Path -LiteralPath $Live)) {
        Move-Item -LiteralPath $Backup -Destination $Live -ErrorAction Stop
    }
    throw "NOX_V27_ROLLBACK_AFTER_FAILURE: $errorText"
}
