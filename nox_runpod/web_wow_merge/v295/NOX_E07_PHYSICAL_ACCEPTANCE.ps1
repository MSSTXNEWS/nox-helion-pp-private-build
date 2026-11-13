#requires -Version 5.1
<#
NOX HELION V29.5 physical Windows-only inspection.
Read-only with respect to live NOX, models, S03, and GPU. Does not reboot,
restart services, kill a generation or make source changes. Unknown=HOLD.
A two-stage BeforeRestart/AfterRestart owner-operated S03 continuity protocol is
available without stopping the current service automatically.
#>
[CmdletBinding()]
param(
 [string]$Root='C:\NOX',
 [int]$Port=8766,
 [string]$LiveWeb='',
 [string]$ExePath='',
 [ValidateSet('Current','BeforeRestart','AfterRestart')][string]$Phase='Current'
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$Stage=Join-Path $Root 'builds\NOX_V29_4_VERIFIED_STAGE'
$Proof=Join-Path $Stage 'NOX_E07_NATIVE_ACCEPTANCE'
$WebSha='166becb90fce63e2db3f9a74281d756995844552cddb7b67a0ac4bd67a190aa0'
$D02Sha='f3fc804d238146ffe42c50103d3e04c9736b8b587c6572987f59b61a6112eb17'
$Receipt=[ordered]@{
 schema='NOX-E07-NATIVE-PHYSICAL-ACCEPTANCE-v1'
 utc=(Get-Date).ToUniversalTime().ToString('o')
 phase=$Phase
 original_source_lock='HOLD'
 running_onehost='HOLD'
 installed_approved_D02='HOLD'
 active_web_root_sha='HOLD'
 same_running_EXE_SHA='HOLD'
 s03_readback='HOLD'
 s03_restart_continuity='HOLD'
 stop_idle_nonexistent_only='HOLD'
 active_ollama_generation_stop='NOT_RUN_NO_UNSAFE_INJECTION'
 ollama_local_status='HOLD'
 safe70_sensor_3_reads='HOLD'
 safe70_trip_proven='HOLD_NOT_TRIGGERED_TO_PROTECT_HARDWARE'
 ru_sapi_wav='HOLD'
 es_sapi_wav='HOLD'
 ru_es_speech_recognition='HOLD_NOT_TESTED'
 optimizer_student_weight_delta='HOLD_NO_INDEPENDENT_TRAINER_RECEIPT'
 independent_WPF_WebView2_visual_E07='HOLD_NO_SCREENSHOT_PIXEL_ACCEPTANCE'
 production_modified=$false
 release_accepted=$false
}
if(-not (Test-Path -LiteralPath $Stage -PathType Container)) {throw 'NOX_E07_STAGING_ABSENT'}
if(-not (Test-Path -LiteralPath (Join-Path $Stage 'NOX_V294_STAGE_RECEIPT.json') -PathType Leaf)) {throw 'NOX_E07_SOURCE_RECEIPT_ABSENT'}
$Staging=Get-Content -LiteralPath (Join-Path $Stage 'NOX_V294_STAGE_RECEIPT.json') -Raw -Encoding UTF8|ConvertFrom-Json
if($Staging.web_sha256 -cne $WebSha -or $Staging.production_modified -ne $false -or $Staging.release_accepted -ne $false){throw 'NOX_E07_UNTRUSTED_STAGE'}
if((Get-FileHash -LiteralPath (Join-Path $Stage 'site\index.html') -Algorithm SHA256).Hash.ToLowerInvariant() -cne $D02Sha){throw 'NOX_E07_ORIGINAL_HOME_CHANGED'}
$Receipt.original_source_lock='PASS_V294_STAGED_1085_SOURCE_LOCK'
[void](New-Item -ItemType Directory -Path $Proof -Force)
$api='http://127.0.0.1:'+ $Port
function Read-Nox($route){
 $u=$api+$route
 return Invoke-RestMethod -Method Get -Uri $u -TimeoutSec 7 -ErrorAction Stop
}
$server=$null;$history=$null;$memory=$null
try{
 $server=Read-Nox '/api/nox/status'
 if(($server.host -eq 'NOX_CHAT_V24.1' -and $server.safe70 -ne $null) -or
    ($server.backend -eq 'EXISTING_NATIVE_ONEHOST' -and $server.native_p02_bound -eq $true)){
  $Receipt.running_onehost='PASS_IDENTITY_LOOPBACK_ONLY'
 }else{$Receipt.running_onehost='HOLD_UNKNOWN_BACKEND'}
}catch{$Receipt.running_onehost='HOLD_UNREACHABLE'}
if($Receipt.running_onehost -like 'PASS*'){
 try{
  $memory=Read-Nox '/api/nox/memory';$history=Read-Nox '/api/nox/history'
  if($memory.status -eq 'READY' -and $null -ne $memory.stats -and $null -ne $memory.segments -and
     $history.status -eq 'READY' -and $null -ne $history.dialogs){
   $Receipt.s03_readback='PASS_READ_API_NOT_RESTART'
  }
 }catch{$Receipt.s03_readback='HOLD_API_UNREACHABLE'}
 try{
  $model=Read-Nox '/api/nox/progress'
  if($model.schema -eq 'nox-progress-receipt-v1' -and $model.status -eq 'VERIFIED_COMPLETE' -and
     $model.weightUpdateVerified -eq $true -and $model.windowsSyncVerified -eq $true -and
     $model.attestation -eq 'LOCAL_WEIGHT_AND_TRAINER_STATE_SHA256_CHECKED'){
   $Receipt.optimizer_student_weight_delta='HOLD_REPORTED_COMPLETE_BUT_NOT_INDEPENDENTLY_REPLAYED'
  }
 }catch{}
 try{
  $body=@{request_id='NOX_E07_NO_SUCH_REQUEST_PING';} | ConvertTo-Json -Compress
  $stop=Invoke-RestMethod -Method Post -Uri ($api+'/api/nox/stop') -TimeoutSec 7 -ContentType 'application/json' -Body $body
  if($stop.status -eq 'IDLE' -and [int]$stop.stopped -eq 0){$Receipt.stop_idle_nonexistent_only='PASS_NO_OTHER_CHAT_CANCELLED'}
 }catch{$Receipt.stop_idle_nonexistent_only='HOLD'}
 $samples=@()
 for($i=0;$i -lt 3;$i++){
  try{
   $snap=Read-Nox '/api/nox/pc-load'
   if($null -ne $snap.gpu_hot_spot_c -and [double]$snap.gpu_hot_spot_c -gt 0 -and [double]$snap.gpu_hot_spot_c -lt 130){
    $samples+=,[double]$snap.gpu_hot_spot_c
   }
  }catch{}
  if($i -lt 2){Start-Sleep -Milliseconds 700}
 }
 if($samples.Count -eq 3){
  $max=($samples|Measure-Object -Maximum).Maximum
  $Receipt.safe70_sensor_3_reads=if($max -lt 70){'PASS_THREE_READINGS_BELOW70_NO_TRIP'}else{'HOLD_HOTSPOT_GE70'}
 }
}
try{
 $url='http://127.0.0.1:11434/api/tags';$tags=Invoke-RestMethod -Method Get -Uri $url -TimeoutSec 5
 if($null -ne $tags.models){$Receipt.ollama_local_status='PASS_API_READ_ONLY_NOT_GENERATION'}
}catch{$Receipt.ollama_local_status='HOLD_OLLAMA_UNAVAILABLE'}
if($LiveWeb -ne ''){
 try{
  $full=[IO.Path]::GetFullPath($LiveWeb)
  $rootFull=[IO.Path]::GetFullPath($Root).TrimEnd('\')+'\'
  if(-not $full.StartsWith($rootFull,[StringComparison]::OrdinalIgnoreCase)){throw 'OUTSIDE_ROOT'}
  if((Get-Item -LiteralPath $full).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'REPARSE_POINT'}
  $index=Join-Path $full 'index.html'
  if((Get-FileHash -LiteralPath $index -Algorithm SHA256).Hash.ToLowerInvariant() -cne $D02Sha){throw 'D02_CHANGED'}
  $Receipt.installed_approved_D02='PASS_EXACT_ORIGINAL_SHA'
  $manFile=Join-Path $Stage 'site\SOURCE_MANIFEST_V29.json'
  $manifest=Get-Content -LiteralPath $manFile -Raw -Encoding UTF8|ConvertFrom-Json
  $changed=0
  foreach($entry in $manifest.PSObject.Properties){
   $target=Join-Path $full ($entry.Name.Replace('/','\'))
   if(-not (Test-Path -LiteralPath $target -PathType Leaf)){$changed++;continue}
   if((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -cne $entry.Value.sha256){$changed++}
  }
  $Receipt.active_web_root_sha=if($changed -eq 0){'PASS_1085_WEB_FILES'}else{"HOLD_WEB_DRIFT_$changed"}
 }catch{$Receipt.active_web_root_sha='HOLD_WEB_ROOT_INVALID'}
}
if($ExePath -ne ''){
 try{
  $resolved=(Resolve-Path -LiteralPath $ExePath).Path
  $h=(Get-FileHash -LiteralPath $resolved -Algorithm SHA256).Hash.ToLowerInvariant()
  $found=@(Get-CimInstance Win32_Process -ErrorAction Stop|Where-Object {$_.ExecutablePath -eq $resolved})
  if($found.Count -gt 0){$Receipt.same_running_EXE_SHA='PASS_PROCESS_IMAGE_SHA_'+$h}
 }catch{$Receipt.same_running_EXE_SHA='HOLD_EXE_UNKNOWN'}
}
try{
 Add-Type -AssemblyName System.Speech -ErrorAction Stop
 $tts=[System.Speech.Synthesis.SpeechSynthesizer]::new()
 try{
  $voices=@($tts.GetInstalledVoices()|Where-Object {$_.Enabled})
  foreach($l in @('ru','es')){
   $vo=@($voices|Where-Object {$_.VoiceInfo.Culture.Name.StartsWith($l+'-')})
   if($vo.Count -eq 0){$Receipt[($l+'_sapi_wav')]='HOLD_VOICE_NOT_INSTALLED';continue}
   $p=Join-Path $Proof ('tts_'+$l+'.wav')
   if(Test-Path -LiteralPath $p){$Receipt[($l+'_sapi_wav')]='HOLD_EXISTING_WAV_NO_OVERWRITE';continue}
   $tts.SelectVoice($vo[0].VoiceInfo.Name);$tts.SetOutputToWaveFile($p)
   try{$tts.Speak($(if($l -eq 'ru'){'Проверка голоса NOX.'}else{'Prueba de voz NOX.'}))}finally{$tts.SetOutputToNull()}
   $bytes=[IO.File]::ReadAllBytes($p)
   if($bytes.Length -ge 44 -and [Text.Encoding]::ASCII.GetString($bytes,0,4) -eq 'RIFF'){
    $Receipt[($l+'_sapi_wav')]='PASS_REAL_WAVE_SHA_'+(Get-FileHash $p -Algorithm SHA256).Hash.ToLowerInvariant()
   }
  }
 }finally{$tts.Dispose()}
}catch{$Receipt.ru_sapi_wav='HOLD_SYSTEM_SPEECH_UNAVAILABLE';$Receipt.es_sapi_wav='HOLD_SYSTEM_SPEECH_UNAVAILABLE'}
# Real continuity requires operator-controlled restart and a new process instance.
$Baseline=Join-Path $Proof 'S03_BEFORE_RESTART.json'
if($Phase -eq 'BeforeRestart' -and $Receipt.s03_readback -like 'PASS*'){
 try{
  $owner=(Get-NetTCPConnection -LocalPort $Port -State Listen|Select-Object -First 1).OwningProcess
  if($owner){
   $proc=Get-Process -Id $owner
   $state=[ordered]@{utc=$Receipt.utc;pid=[int]$owner;started=$proc.StartTime.ToUniversalTime().ToString('o');
        dialog_ids=@($history.dialogs|ForEach-Object {$_.id});s03_levels=@($memory.levels.PSObject.Properties.Name)}
   $state|ConvertTo-Json -Depth 6|Set-Content -LiteralPath $Baseline -Encoding UTF8
   $Receipt.s03_restart_continuity='BEFORE_SNAPSHOT_SAVED_RESTART_NOT_PERFORMED'
  }
 }catch{$Receipt.s03_restart_continuity='HOLD_NO_PROCESS_OWNER'}
}
if($Phase -eq 'AfterRestart' -and $Receipt.s03_readback -like 'PASS*' -and (Test-Path -LiteralPath $Baseline)){
 try{
  $old=Get-Content -LiteralPath $Baseline -Raw -Encoding UTF8|ConvertFrom-Json
  $owner=(Get-NetTCPConnection -LocalPort $Port -State Listen|Select-Object -First 1).OwningProcess
  $proc=Get-Process -Id $owner
  $started=$proc.StartTime.ToUniversalTime()
  if($started -le [DateTime]$old.started){throw 'NO_RESTART_OBSERVED'}
  $current=@($history.dialogs|ForEach-Object {$_.id})
  foreach($id in $old.dialog_ids){if($id -notin $current){throw 'DIALOG_MISSING_AFTER_RESTART'}}
  $Receipt.s03_restart_continuity='PASS_REAL_DIAGNOSTIC_BEFORE_AFTER_DIFFERENT_PROCESS'
 }catch{$Receipt.s03_restart_continuity='HOLD_NOT_RESTARTED_OR_MISSING_DIALOG'}
}
$receiptPath=Join-Path $Proof ('NOX_E07_'+$Phase+'_'+(Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffZ')+'.json')
$Receipt|ConvertTo-Json -Depth 8|Set-Content -LiteralPath $receiptPath -Encoding UTF8
Write-Output ($Receipt|ConvertTo-Json -Depth 8)
Write-Output "NOX_E07_RECEIPT: $receiptPath"
Write-Output 'NOX_E07_NATIVE_PHYSICAL_INSPECTED_NO_PRODUCTION_MUTATIONS; UNPROVEN_GATES_REMAIN_HOLD'
