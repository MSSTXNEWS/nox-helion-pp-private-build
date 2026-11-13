#requires -Version 5.1
# Explicit opt-in SHA-locked source patch of the SAME existing NOX PC backend.
# No service restart, no SQLite writes, and no deletion of the original source.
[CmdletBinding()]
param(
  [string]$Root='C:\NOX',
  [string]$NativeAppDir='',
  [switch]$Apply,
  [string]$ApproveExactWebSHA=''
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$ExpectedWebSha='166becb90fce63e2db3f9a74281d756995844552cddb7b67a0ac4bd67a190aa0'
$Original=@{
 'nox_chat_server.py'='4d5766cdd98333c9bfdfd394029debc07224d08b59ac54bdc60565130cd6143a'
 'nox_voice.py'='dd34f8427001fdc0163b66f2d825f6ea487bb38435dc89d8acdc799ed4a82fea'
}
$Patched=@{
 'nox_chat_server.py'='3ec3e4a8a6fcc53ea5a1cc102556451107fcfa7c8d110965f843e4febd7a9cb5'
 'nox_voice.py'='f3e437a053fe53955c9df95d607e12aa22ad2b0cdd49da3fd02349bb3c683139'
}
$Stage=Join-Path $Root 'builds\NOX_V29_4_VERIFIED_STAGE'
$Base=Join-Path $Stage 'native_source'
if (-not (Test-Path -LiteralPath (Join-Path $Stage 'NOX_V294_STAGE_RECEIPT.json'))) {throw 'NOX_V294_STAGE_REQUIRED'}
if (-not $NativeAppDir) {
  $candidates=@()
  foreach($parent in @((Join-Path $Root 'chat'),(Join-Path $Root 'helion'))){
    if(Test-Path -LiteralPath $parent -PathType Container){
      $candidates+=@(Get-ChildItem -LiteralPath $parent -Filter 'nox_chat_server.py' -File -Recurse -ErrorAction SilentlyContinue | Select-Object -ExpandProperty DirectoryName)
    }
  }
  $candidates=@($candidates | Sort-Object -Unique)
  if($candidates.Count -ne 1){throw "NOX_NATIVE_APP_DIR_NOT_UNIQUE_OR_MISSING: $($candidates.Count)"}
  $NativeAppDir=$candidates[0]
}
if (-not (Test-Path -LiteralPath $NativeAppDir -PathType Container)) {throw 'NOX_NATIVE_APP_DIR_MISSING'}
$RootCanonical=[System.IO.Path]::GetFullPath($Root).TrimEnd('\')+'\'
$AppCanonical=[System.IO.Path]::GetFullPath($NativeAppDir).TrimEnd('\')+'\'
if (-not $AppCanonical.StartsWith($RootCanonical,[StringComparison]::OrdinalIgnoreCase)) {throw 'NOX_NATIVE_PATH_OUTSIDE_ROOT_HOLD'}
$changed=@()
foreach ($name in @('nox_chat_server.py','nox_voice.py')) {
 $live=Join-Path $NativeAppDir $name
 $staged=Join-Path $Base $name
 if (-not (Test-Path -LiteralPath $live -PathType Leaf) -or -not (Test-Path -LiteralPath $staged -PathType Leaf)){throw "NOX_SOURCE_MISSING: $name"}
 foreach($path in @($live,$staged)){
   if (((Get-Item -LiteralPath $path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {throw "NOX_SOURCE_REPARSE_HOLD: $path"}
 }
 $localSha=(Get-FileHash -LiteralPath $live -Algorithm SHA256).Hash.ToLowerInvariant()
 $updatedSha=(Get-FileHash -LiteralPath $staged -Algorithm SHA256).Hash.ToLowerInvariant()
 if ($updatedSha -cne $Patched[$name]){throw "NOX_PATCHED_SOURCE_SHA_HOLD: $name"}
 if ($localSha -cne $Original[$name] -and $localSha -cne $Patched[$name]){throw "NOX_LIVE_SOURCE_UNKNOWN_SHA_HOLD: $name"}
 if ($localSha -cne $Patched[$name]){$changed+=,$name}
}
if (-not $Apply){
 Write-Output "NOX_V294_NATIVE_PRECHECK: $NativeAppDir"
 Write-Output "NEEDS_UPDATE_COUNT: $($changed.Count); no live source changed"
 exit 0
}
if ($ApproveExactWebSHA -cne $ExpectedWebSha) {throw 'NOX_OWNER_EXACT_SOURCE_SHA_APPROVAL_REQUIRED'}
if ($changed.Count -eq 0){Write-Output 'NOX_V294_NATIVE_ALREADY_PATCHED_SOURCE_SHA_PASS';exit 0}
$ArchiveDir=Join-Path $Root 'archive'
$stamp=(Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ')
$Backups=Join-Path $ArchiveDir ('NOX_NATIVE_PRE_V294_'+$stamp)
if(Test-Path -LiteralPath $Backups){throw 'NOX_BACKUP_ALREADY_EXISTS'}
[void](New-Item -ItemType Directory -Path $Backups -Force)
$updated=@()
try{
 foreach($name in $changed){
  $live=Join-Path $NativeAppDir $name
  $old=Join-Path $Backups $name
  Copy-Item -LiteralPath $live -Destination $old -ErrorAction Stop
  if ((Get-FileHash $old -Algorithm SHA256).Hash.ToLowerInvariant() -cne $Original[$name]){throw "NOX_BACKUP_MISMATCH: $name"}
 }
 foreach($name in $changed){
  $live=Join-Path $NativeAppDir $name
  $staged=Join-Path $Base $name
  $temporary=$live+'.nox_v294_new'
  if (Test-Path -LiteralPath $temporary){throw "NOX_TEMP_PATCH_EXISTS: $name"}
  Copy-Item -LiteralPath $staged -Destination $temporary
  if ((Get-FileHash $temporary -Algorithm SHA256).Hash.ToLowerInvariant() -cne $Patched[$name]) {throw "NOX_TEMP_PATCH_SHA_FAIL: $name"}
  [System.IO.File]::Replace($temporary,$live,$null)
  $updated+=,$name
  if ((Get-FileHash $live -Algorithm SHA256).Hash.ToLowerInvariant() -cne $Patched[$name]) {throw "NOX_POST_PATCH_SHA_FAILED: $name"}
 }
 $receipt=[ordered]@{schema='NOX-V294-SAME-BACKEND-PATCH-v1';utc=(Get-Date).ToUniversalTime().ToString('o');app=$NativeAppDir;patches=$updated;backups=$Backups;chat_process_restarted=$false;s03_db_modified=$false;model_weights_modified=$false;production_web_modified=$false;native_activation_after_existing_process_restart='NOT_VERIFIED';release_accepted=$false}
 $receipt|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $Backups 'PATCH_RECEIPT.json') -Encoding UTF8
 Write-Output ('NOX_V294_SAME_BACKEND_PATCHED_ON_DISK_RESTART_NOT_PERFORMED: '+($updated -join ','))
}
catch {
 $errorText=$_.Exception.Message
 foreach($name in $updated){
  $source=Join-Path $Backups $name
  $live=Join-Path $NativeAppDir $name
  if((Test-Path $source) -and (Test-Path $live)){
   $tmp=$live+'.nox_v294_rollback'
   Copy-Item -LiteralPath $source -Destination $tmp
   [System.IO.File]::Replace($tmp,$live,$null)
  }
 }
 throw ('NOX_V294_ROLLBACK_AFTER_FAILURE: '+$errorText)
}
