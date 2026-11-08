# NOX R8/V16 owner-machine readiness probe. Read-only: no installs, downloads, deletes or training.
# instructions_version: 0.0.6
[CmdletBinding()]
param(
  [string]$Root = 'C:\NOX_HELION',
  [string]$OllamaUrl = 'http://127.0.0.1:11434',
  [switch]$RequireGpuTraining
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$checks = [System.Collections.Generic.List[object]]::new()
function Add-Check([string]$Name,[string]$Status,[string]$Detail) {
  $checks.Add([ordered]@{name=$Name;status=$Status;detail=$Detail})
}
# Do not execute or open user content. Data paths are informational only.
Add-Check 'nox_root' $(if (Test-Path -LiteralPath $Root -PathType Container) {'PASS'} else {'HOLD'}) $Root
$ollamaModels = @()
try {
  $uri = ([Uri]::new($OllamaUrl.TrimEnd('/') + '/api/tags'))
  if ($uri.Host -notin @('127.0.0.1','localhost','::1')) { throw 'LOOPBACK_ONLY' }
  $response = Invoke-RestMethod -Method Get -Uri $uri -TimeoutSec 5
  $ollamaModels = @($response.models | ForEach-Object { [string]$_.name })
  Add-Check 'ollama_loopback' 'PASS' ('models=' + $ollamaModels.Count)
} catch { Add-Check 'ollama_loopback' 'HOLD' $_.Exception.Message }
foreach($label in @('qwen3-embedding:0.6b')) {
  $found = @($ollamaModels | Where-Object { $_ -eq $label }).Count -gt 0
  Add-Check ('required_model_' + $label) $(if($found){'PASS'}else{'HOLD'}) $(if($found){'exact installed tag'}else{'not confirmed by local /api/tags'})
}
$qwenChat = @($ollamaModels | Where-Object { $_ -match '^qwen' -and $_ -notmatch 'embedding' })
Add-Check 'qwen_chat_model' $(if($qwenChat.Count){'PASS'}else{'HOLD'}) ($qwenChat -join ',')
try {
  $tool = Get-Command nvidia-smi -ErrorAction Stop
  $gpu = @(& $tool.Source --query-gpu=name,temperature.gpu,memory.total --format=csv,noheader 2>$null)
  if ($LASTEXITCODE -ne 0 -or -not $gpu) { throw 'NVML_UNAVAILABLE' }
  Add-Check 'nvidia_gpu_sensor' 'PASS' ($gpu -join '; ')
} catch { Add-Check 'nvidia_gpu_sensor' 'HOLD' $_.Exception.Message }
try {
  $sound = @(Get-CimInstance Win32_SoundDevice -ErrorAction Stop | Where-Object { $_.Status -eq 'OK' })
  Add-Check 'windows_audio_device' $(if($sound.Count){'PASS'}else{'HOLD'}) ('active_audio_devices=' + $sound.Count + '; microphone ASR not attested')
} catch { Add-Check 'windows_audio_device' 'HOLD' $_.Exception.Message }
$exe = @(Get-ChildItem -LiteralPath $Root -Filter 'NOX.HELION.exe' -Recurse -File -ErrorAction SilentlyContinue | Select-Object -First 2)
Add-Check 'installed_nox_exe' $(if($exe.Count -eq 1){'PASS'}else{'HOLD'}) ('found=' + $exe.Count + '; does not prove UI or behavior')
if ($exe.Count -eq 1) {
  Add-Check 'nox_exe_sha256' 'INFO' ((Get-FileHash -LiteralPath $exe[0].FullName -Algorithm SHA256).Hash.ToLowerInvariant())
}
# These require an interactive end-to-end test: never infer PASS from device presence.
foreach($name in @('qwen_stream_stop_sqlite_restart_e2e','rag_real_embedding_ingest_search','voice_ru_es_microphone_asr_e2e','qlora_real_checkpoint_and_merge','d02_wow_visual_acceptance','legacy_go_wails_parity')) {
  Add-Check $name 'HOLD' 'Requires separate physical end-to-end evidence'
}
$report = [ordered]@{
 schema='NOX_R8_OWNER_READINESS_V1'
 instructions_version='0.0.6'
 created_utc=[DateTime]::UtcNow.ToString('o')
 execution='READ_ONLY_OWNER_MACHINE'
 checks=@($checks.ToArray())
 release='HOLD'
}
$report | ConvertTo-Json -Depth 6
if ($RequireGpuTraining -and @($checks | Where-Object { $_.name -eq 'nvidia_gpu_sensor' -and $_.status -eq 'HOLD' }).Count) { exit 2 }
