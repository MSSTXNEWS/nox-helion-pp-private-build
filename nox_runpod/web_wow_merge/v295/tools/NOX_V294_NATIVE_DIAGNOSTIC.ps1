#requires -Version 5.1
# NOX V29.4: real read-only local OneHost, S03, RU+ES SAPI, SAFE70 sensor diagnostics.
# No live source changes, no user chat STOP or process restarts.
[CmdletBinding()]
param(
 [string]$Root = 'C:\NOX',
 [int]$Port = 8766,
 [string]$ExePath = ''
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Stage = Join-Path $Root 'builds\NOX_V29_4_VERIFIED_STAGE'
if (-not (Test-Path -LiteralPath (Join-Path $Stage 'NOX_V294_STAGE_RECEIPT.json') -PathType Leaf)) {
 throw 'NOX_V294_VERIFIED_STAGE_REQUIRED_FIRST'
}
$Report = [ordered]@{
 schema='NOX-V29.4-NATIVE-READONLY-DIAGNOSTIC-v1'
 collected_utc=(Get-Date).ToUniversalTime().ToString('o')
 host='HOLD'
 history='HOLD'
 s03='HOLD'
 progress='HOLD'
 stop_idle_handshake='HOLD'
 ru_tts='HOLD'
 es_tts='HOLD'
 gpu_hotspot_three_samples='HOLD'
 exe_sha256='HOLD'
 s03_restart_persistence_on_user_machine='NOT_RUN'
 active_ollama_generation_stop_on_user_machine='NOT_RUN'
 independent_WPF_WebView2_E07='NOT_RUN'
 production_modified=$false
 release_accepted=$false
}
$Base='http://127.0.0.1:'+ $Port
function Get-Nox([string]$Path) {
 return Invoke-RestMethod -Method Get -Uri ($Base+$Path) -TimeoutSec 5 -ErrorAction Stop
}
try {
 $status = Get-Nox '/api/nox/status'
 if ($status.host -eq 'NOX_CHAT_V24.1' -or ($status.backend -eq 'EXISTING_NATIVE_ONEHOST' -and $status.native_p02_bound -eq $true)) {
  $Report.host = 'REAL_LOOPBACK_IDENTITY_PASS'
 }
} catch { $Report.host = 'HOLD_UNREACHABLE_' + $_.Exception.GetType().Name }
if ($Report.host -eq 'REAL_LOOPBACK_IDENTITY_PASS') {
 try {
  $mem=Get-Nox '/api/nox/memory'
  if ($mem.status -eq 'READY' -and $null -ne $mem.stats -and $null -ne $mem.segments) {$Report.s03='REAL_S03_READ_PASS'}
 } catch { $Report.s03='HOLD_UNAVAILABLE' }
 try {
  $history=Get-Nox '/api/nox/history'
  if ($history.status -eq 'READY' -and $null -ne $history.dialogs) {$Report.history='REAL_DIALOG_HISTORY_READ_PASS'}
 } catch { $Report.history='HOLD_UNAVAILABLE' }
 try {
  $progress=Get-Nox '/api/nox/progress'
  if ($progress.schema -eq 'nox-progress-receipt-v1' -and $progress.status -eq 'VERIFIED_COMPLETE' -and
      $progress.weightUpdateVerified -eq $true -and $progress.windowsSyncVerified -eq $true) {
   $Report.progress='RECEIPT_CLAIM_VERIFIED_NOT_INDEPENDENT_GPU'
  } else {$Report.progress='HOLD_NO_FULL_WEIGHT_PROOF'}
 } catch { $Report.progress='HOLD_UNAVAILABLE' }
 try {
  $body=@{request_id='NOX_QA_NONEXISTENT_REQUEST_ID_NO_LIVE_ABORT'} | ConvertTo-Json
  $ack=Invoke-RestMethod -Method Post -Uri ($Base+'/api/nox/stop') -Body $body -ContentType 'application/json' -TimeoutSec 5
  if ($ack.status -eq 'IDLE' -and $ack.stopped -eq 0) {$Report.stop_idle_handshake='PASS_NONEXISTENT_ID_NO_USER_CHAT_INTERRUPTED'}
  else {$Report.stop_idle_handshake='HOLD_UNEXPECTED_STOP_RESPONSE'}
 } catch { $Report.stop_idle_handshake='HOLD_UNAVAILABLE' }
 $sensorValues=@()
 for ($i=0; $i -lt 3; $i++) {
  try {
   $snap=Get-Nox '/api/nox/pc-load'
   if ($null -ne $snap.gpu_hot_spot_c -and [double]$snap.gpu_hot_spot_c -gt 0) {$sensorValues += [double]$snap.gpu_hot_spot_c}
  } catch {}
  if ($i -lt 2) {Start-Sleep -Seconds 1}
 }
 if ($sensorValues.Count -eq 3) {
  $max=($sensorValues | Measure-Object -Maximum).Maximum
  if ($max -ge 70) {$Report.gpu_hotspot_three_samples='HOLD_HOTSPOT_LIMIT_REACHED'}
  else {$Report.gpu_hotspot_three_samples='PASS_REAL_READINGS_BELOW70_NOT_TRIP_TEST'}
 }
}
try {
 Add-Type -AssemblyName System.Speech -ErrorAction Stop
 $s=New-Object System.Speech.Synthesis.SpeechSynthesizer
 try {
  $voices=@($s.GetInstalledVoices() | Where-Object {$_.Enabled})
  foreach($language in @('ru','es')) {
   $matched=@($voices | Where-Object {$_.VoiceInfo.Culture.Name -like ($language+'-*')})
   if ($matched.Count -gt 0) {
    $out=Join-Path $Stage ('NOX_V294_NATIVE_TTS_'+$language+'.wav')
    if (Test-Path -LiteralPath $out) {throw "NOX_TTS_OUTPUT_PREEXISTS_$language"}
    $s.SelectVoice($matched[0].VoiceInfo.Name)
    $s.SetOutputToWaveFile($out)
    try {
     $speech=if($language -eq 'ru') {'Привет, это проверка NOX.'} else {'Hola, esto es una prueba de NOX.'}
     $s.Speak($speech)
    } finally {$s.SetOutputToNull()}
    $wav=[System.IO.File]::ReadAllBytes($out)
    if ($wav.Length -ge 44 -and [Text.Encoding]::ASCII.GetString($wav,0,4) -eq 'RIFF' -and
        [Text.Encoding]::ASCII.GetString($wav,8,4) -eq 'WAVE') {
     $Report[($language+'_tts')]='PASS_REAL_WINDOWS_SAPI_WAV_SHA_'+(Get-FileHash -LiteralPath $out -Algorithm SHA256).Hash.ToLowerInvariant()
    }
   } else {$Report[($language+'_tts')]='HOLD_NO_INSTALLED_WINDOWS_SAPI_VOICE'}
  }
 } finally {$s.Dispose()}
} catch { $Report.ru_tts='HOLD_SAPI_'+$_.Exception.GetType().Name; $Report.es_tts='HOLD_SAPI_'+$_.Exception.GetType().Name }
if ($ExePath -ne '' -and (Test-Path -LiteralPath $ExePath -PathType Leaf)) {
 $Report.exe_sha256=(Get-FileHash -LiteralPath $ExePath -Algorithm SHA256).Hash.ToLowerInvariant()
}
$outReceipt=Join-Path $Stage 'NOX_V294_NATIVE_DIAGNOSTIC_RECEIPT.json'
$Report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $outReceipt -Encoding UTF8
Write-Output ($Report | ConvertTo-Json -Depth 8)
Write-Output 'NOX_V294_NATIVE_READONLY_DIAGNOSTICS_DONE; FULL_E07_STILL_HOLD'
