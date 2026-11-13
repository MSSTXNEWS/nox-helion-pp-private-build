#requires -Version 5.1
<#
NOX HELION V25 — existing OneHost web-root promotion with immediate rollback.
No second server, no changes to Ollama, model weights, S03 or training.
Default: verify-only, -Apply is an explicit local owner action.
#>
[CmdletBinding()]
param(
    [switch]$Apply,
    [string]$Root = 'C:\NOX',
    [string]$Archive = 'C:\NOX\incoming\NOX_WEB_WOW_V25_PC_UNIFIED_SOURCE_CANDIDATE.zip'
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ExpectedSha = '9556b5be3e8e9ce24eee7c6ae77a62ab8c8d58fe145568a35981565e14240145'
$Live = Join-Path $Root 'chat\NOX_CHAT_V24\web'
$Backend = Join-Path $Root 'chat\NOX_CHAT_V24\app\nox_chat_server.py'
$Builds = Join-Path $Root 'builds\NOX_WEB_WOW_V25_STAGING'
$Archives = Join-Path $Root 'archive'

function Require-200([string]$Url) {
    $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 7
    if ([int]$response.StatusCode -ne 200) {
        throw "NOX_HTTP_HOLD $Url $($response.StatusCode)"
    }
    return [int]$response.Content.Length
}
function Audit-Current {
    if (-not (Test-Path -LiteralPath $Live -PathType Container)) { throw "NOX_LIVE_WEB_MISSING: $Live" }
    if (-not (Test-Path -LiteralPath $Backend -PathType Leaf)) { throw "NOX_EXISTING_SERVER_MISSING: $Backend" }
    $serverText = Get-Content -LiteralPath $Backend -Raw -Encoding UTF8
    if (-not $serverText.Contains('WEB = os.path.join(ROOT, "web")')) {
        throw 'NOX_EXISTING_ONEHOST_WEB_CONTRACT_CHANGED'
    }
    $webItem = Get-Item -LiteralPath $Live
    if ($webItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
        throw 'NOX_LIVE_WEB_REPARSE_HOLD'
    }
    [void](Require-200 'http://127.0.0.1:8766/api/nox/status')
    [void](Require-200 'http://127.0.0.1:8766/api/nox/memory')
}

if (-not (Test-Path -LiteralPath $Archive -PathType Leaf)) {
    throw "NOX_ARCHIVE_MISSING: $Archive"
}
$actualSha = (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualSha -ne $ExpectedSha) {
    throw "NOX_ARCHIVE_SHA_HOLD: expected $ExpectedSha actual $actualSha"
}
Audit-Current
if (-not (Test-Path -LiteralPath $Builds)) { [void](New-Item -ItemType Directory -Path $Builds -Force) }
$Tag = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ')
$Stage = Join-Path $Builds "staging_$Tag"
if (Test-Path -LiteralPath $Stage) { throw 'NOX_STAGING_PREEXISTS' }
Expand-Archive -LiteralPath $Archive -DestinationPath $Stage
$StagedSite = Join-Path $Stage 'site'
$StagedReceipt = Join-Path $Stage 'NOX_PHYSICAL_MERGE_RECEIPT.json'
if (-not (Test-Path -LiteralPath $StagedSite -PathType Container)) { throw 'NOX_SITE_NOT_IN_ZIP' }
if (-not (Test-Path -LiteralPath $StagedReceipt -PathType Leaf)) { throw 'NOX_RECEIPT_MISSING' }
$R = Get-Content -LiteralPath $StagedReceipt -Raw -Encoding UTF8 | ConvertFrom-Json
if ($R.release_accepted -ne $false -or $R.production_modified -ne $false -or
    $R.status -ne 'SOURCE_MERGED_PHYSICAL_ONEHOST_QA_HOLD') {
    throw 'NOX_UNEXPECTED_PRODUCTION_OR_RELEASE_CLAIM'
}
$D02 = Join-Path $StagedSite 'index.html'
$D02Hash = (Get-FileHash -LiteralPath $D02 -Algorithm SHA256).Hash.ToLowerInvariant()
if ($D02Hash -ne $R.original_index_sha256 -or $D02Hash -ne $R.merged_index_sha256) {
    throw 'NOX_D02_SHA_MISMATCH'
}
foreach ($required in @('chat.html','memory.html','pc\resonance.html','pc\memory.html','pc\index.html','cinema.html','training.html')) {
    if (-not (Test-Path -LiteralPath (Join-Path $StagedSite $required) -PathType Leaf)) {
        throw "NOX_MERGED_REQUIRED_FILE_MISSING: $required"
    }
}
$preCheck = @{
    event = 'NOX_WEB_WOW_V25_PRECHECK'
    time_utc = (Get-Date).ToUniversalTime().ToString('o')
    zip_sha256 = $actualSha
    original_d02_sha256 = $D02Hash
    owner_apply = [bool]$Apply
    current_web = $Live
    staged_site = $StagedSite
    stage_status = 'SOURCE_STATIC_VERIFIED_WINDOWS_QA_HOLD'
}
$preCheckPath = Join-Path $Stage 'NOX_WINDOWS_PRECHECK.json'
$preCheck | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $preCheckPath -Encoding UTF8
if (-not $Apply) {
    Write-Output "NOX_DRY_RUN_PASS; original web, S03, Ollama and training unchanged."
    Write-Output "Staged: $StagedSite"
    Write-Output "Apply needs explicit -Apply and physical same-host QA."
    exit 0
}
if (-not (Test-Path -LiteralPath $Archives)) { [void](New-Item -ItemType Directory -Path $Archives -Force) }
$Backup = Join-Path $Archives "WEB_PRE_UNIFIED_$Tag"
if (Test-Path -LiteralPath $Backup) { throw 'NOX_BACKUP_PREEXISTS' }
$Promoted = $false
$MovedOriginal = $false
try {
    # Both paths remain on C:, so this is a directory rename, not file deletion.
    Move-Item -LiteralPath $Live -Destination $Backup -ErrorAction Stop
    $MovedOriginal = $true
    Move-Item -LiteralPath $StagedSite -Destination $Live -ErrorAction Stop
    $Promoted = $true
    # The same pre-existing Python server on 127.0.0.1:8766 handles the
    # merged static tree; NO NEW HOST or database is launched here.
    foreach ($route in @('/index.html','/chat.html','/memory.html',
                         '/pc/resonance.html','/pc/memory.html',
                         '/pc/v25/nox-shell-v25.js',
                         '/pc/vendor/fonts/tektur/tektur.css')) {
        [void](Require-200 ("http://127.0.0.1:8766" + $route))
    }
    Audit-Current
    $postD02 = (Get-FileHash -LiteralPath (Join-Path $Live 'index.html') -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($postD02 -ne $D02Hash) { throw 'NOX_D02_CHANGED_AFTER_PROMOTION' }
    $success = @{
        event = 'NOX_WEB_WOW_V25_SAME_HOST_SOURCE_PROMOTED'
        time_utc = (Get-Date).ToUniversalTime().ToString('o')
        archive_sha256 = $actualSha
        backup = $Backup
        live_web = $Live
        onehost_http_static = 'PASS'
        local_api_status_and_s03 = 'PASS_READ_ONLY'
        windows_wow_e07 = 'HOLD'
        independent_exe_qa = 'NOT_RUN'
        model_weights_modified = $false
    }
    $success | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $Stage 'NOX_WINDOWS_PROMOTE_RECEIPT.json') -Encoding UTF8
    Write-Output "NOX_SOURCE_PROMOTED_SAME_HOST; backup preserved: $Backup"
    Write-Output 'NOT FINAL RELEASE: require independent OneHost/STOP/S03/visual WOW30 E07.'
}
catch {
    $errorText = $_.Exception.Message
    if ($Promoted -and (Test-Path -LiteralPath $Live)) {
        $Quarantine = Join-Path $Builds "rejected_web_$Tag"
        Move-Item -LiteralPath $Live -Destination $Quarantine -ErrorAction Stop
    }
    if ($MovedOriginal -and (Test-Path -LiteralPath $Backup) -and -not (Test-Path -LiteralPath $Live)) {
        Move-Item -LiteralPath $Backup -Destination $Live -ErrorAction Stop
    }
    Write-Error ("NOX_PROMOTION_ROLLBACK: " + $errorText)
    throw
}
