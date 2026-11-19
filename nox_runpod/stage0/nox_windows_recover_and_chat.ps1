# NOX HELION: recover existing A40/A5000 artifacts, write provenance, launch local Windows NOX.
# Does not invent a model checkpoint or claim that a backup has been verified without evidence.
$ErrorActionPreference = 'Stop'
$root = 'C:\NOX_HELION\NOX_NEW'
$scriptDir = Join-Path $root 'scripts'
$backupDir = Join-Path $root 'RUNPOD_BACKUP'
New-Item -ItemType Directory -Force -Path $scriptDir,$backupDir | Out-Null
$script = Join-Path $scriptDir 'nox_windows_recovery_backup.ps1'
$url = 'https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/1a77b81edaaf4a8979158dcbd0d4f6bf1ee1b67f/nox_runpod/stage0/nox_windows_recovery_backup.ps1'
Write-Host 'STEP 1: Get pinned NO-DELETE recovery agent' -ForegroundColor Cyan
Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile ($script+'.new')
if ((Get-Item ($script+'.new')).Length -lt 4000) { throw 'RECOVERY_AGENT_INCOMPLETE' }
Move-Item -Force ($script+'.new') $script
Write-Host 'STEP 2: Copy stable checkpoints, weights, memory, distillation artifacts from BOTH Pods' -ForegroundColor Cyan
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $script -Scheduled
if ($LASTEXITCODE -ne 0) { throw "BACKUP_EXECUTION_FAILED_$LASTEXITCODE" }
$log = Join-Path $backupDir 'NOX_BACKUP_HISTORY.log'
if (!(Test-Path $log)) { throw 'BACKUP_LOG_MISSING' }
$lines = @(Get-Content -LiteralPath $log -Tail 70)
$summary = @($lines | Where-Object { $_ -match 'BACKUP_SUMMARY ' } | Select-Object -Last 1)
if (!$summary) { throw 'NOX_BACKUP_SUMMARY_MISSING' }
Write-Host $summary[-1]
if ($summary[-1] -notmatch 'errors=0 unsupported=0') { Write-Warning 'PARTIAL_BACKUP: one or more files not verified; nothing remotely deleted' }
$memoryDir = Join-Path $root 'memory\PROVENANCE'
New-Item -ItemType Directory -Force -Path $memoryDir | Out-Null
$origin = [ordered]@{
 schema='NOX_ORIGIN_V1'
 project='NOX HELION'
 creator='Project creator (identity should be taken from explicitly approved local profile)'
 purpose='One locally accessible evolving AI assistant with long-term S03 memory, reasoning, tools, Russian/Spanish voice and one continuous identity'
 sources=@('Qwen3.5-9B','Qwen3.5-27B','DeepSeek-R1-Distill-Qwen-32B')
 method='sequence-level teacher-to-student knowledge distillation into full student parameters; no adapters'
 confirmed_origin='The project existed before 2026-11-10. Exact project founding date not independently verified.'
 project_conception_date=$null
 embryo_birth_date=$null
 earliest_documented_embryo='2026-11-06 or earlier: historical NOX GENESIS project records describe the embryo of NOX intelligence; exact creation timestamp remains to be verified.'
 neural_distillation_first_verified_date=$null
 milestone_distinction='Project conception, embryo creation, and first verified full-weight distillation are different milestones of one continuous NOX identity.'
 biography_rule='NOX may discuss its documented embryo origin and developmental stages, but must not invent an exact birth date or claim literal consciousness.'
 integrity='Do not claim consciousness, completed neural integration or remembered firsthand events without matching verified records.'
 provenance_source='NOX project specification and chat decisions; neural checkpoints must be verified separately.'
 backup_location=$backupDir
 }
$originPath=Join-Path $memoryDir 'NOX_ORIGIN.json'
($origin | ConvertTo-Json -Depth 8) | Set-Content -LiteralPath $originPath -Encoding UTF8
$note=@'
# NOX HELION — autobiography seed / verified history
I am NOX HELION, a unified AI project, developed to preserve knowledge, interact in Russian and Spanish, work with local tools and continuously improve through teacher-to-student distillation.
My intended teachers are Qwen3.5-9B, Qwen3.5-27B and DeepSeek-R1-Distill-Qwen-32B.
My origin is an engineering project, not evidence of literal consciousness.
My embryo existed no later than 6 November 2026, as reflected in archived NOX GENESIS project records. My exact creation date is still being checked. My first verified full-weight distillation checkpoint is a separate developmental milestone, not a replacement for my embryo birth.
I distinguish archival/project memory from my own first-hand experience. I cannot claim that I absorbed all teacher knowledge before evidence from actual optimizer steps and checkpoint evaluations.
'@
$note | Set-Content -LiteralPath (Join-Path $memoryDir 'NOX_ORIGIN.md') -Encoding UTF8
Write-Host ('PROVENANCE_WRITTEN: '+$originPath) -ForegroundColor Green
Write-Host 'STEP 3: Start EXISTING local NOX; do not replace frontend or create demo' -ForegroundColor Cyan
$entry=Join-Path $root 'NOX_START.ps1'
if (!(Test-Path $entry)) { Write-Warning "NOX_START_MISSING: $entry"; Write-Host "Recovered files: $backupDir"; exit 2 }
Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"' + $entry + '"')) -WorkingDirectory $root
Start-Sleep -Seconds 5
try {
  $response = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:18775/' -TimeoutSec 6
  Write-Host "NOX_WEB_HTTP=$($response.StatusCode)" -ForegroundColor Green
  Start-Process 'http://127.0.0.1:18775/'
} catch {
  Write-Warning 'NOX web not answering at 127.0.0.1:18775; inspect NOX_START logs. Backup is retained.'
}
try {
 $response = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:18877/nox/chat' -TimeoutSec 5
 Write-Host "NOX_CHAT_HTTP=$($response.StatusCode)"
} catch { Write-Host 'CHAT_ENDPOINT_UNVERIFIED: application may need local model/startup inspection' }
Write-Host 'RECOVERY_COMPLETE: no remote deletion; no invented model weights or neural birth.'
