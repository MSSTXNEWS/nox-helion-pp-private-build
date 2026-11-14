# NOX PRIME V8: one local NOX, source-linked memory/SOUL, natural-language
# auto-FORGE, model audit, and SAFE70 compatible teacher->student learning.
# This is functional intelligence, NOT verified subjective consciousness.
# Never removes or merges incompatible original weights or creates second S03.
param(
 [Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{40}$')][string]$SourceSha,
 [switch]$SkipTraining
)
$ErrorActionPreference='Stop'
$root='C:\NOX_HELION\NOX_NEW'
$repo="$root\brain\source\repo"
$source=Split-Path -Parent $MyInvocation.MyCommand.Path
$python=Join-Path $env:USERPROFILE 'NOX_EXPRESS_AI\NOX_TRAINING\train-venv\Scripts\python.exe'
$checks=@(
 'NOX_PRIME_LIVE_V6_BOOT.ps1',
 'NOX_PRIME_DISTILL_RUN_V7.ps1',
 'nox_prime_weight_audit_v1.py',
 'nox_prime_autonomous_router_v1.py',
 'nox_prime_forge_job_v1.py'
)
if (!(Test-Path "$repo\.git") -or !(Test-Path "$root\brain") -or !(Test-Path $python)) {
    throw 'NOX EXISTING GIT/BRAIN/TRAINING PYTHON NOT FOUND; ORIGINALS UNTOUCHED'
}
foreach($name in $checks){
    if(!(Test-Path (Join-Path $source $name))){throw "NOX V8 SOURCE MISSING: $name"}
}
$rev=(& git -C $repo cat-file -t $SourceSha 2>$null)
if($LASTEXITCODE -ne 0 -or $rev -ne 'commit'){
    throw 'NOX SOURCE COMMIT NOT FETCHED; DO NOT RUN UNVERSIONED SOURCES'
}
$receiptFolder="$root\brain\telemetry"
New-Item -ItemType Directory -Path $receiptFolder -Force | Out-Null
$startReceipt=Join-Path $receiptFolder 'prime_activation_v8.json'
$run=@{
  source_sha=$SourceSha
  status='STARTING'
  started_utc=(Get-Date).ToUniversalTime().ToString('o')
  neural_base='Existing qwen3:8b Ollama for chat'
  training_target='Existing Qwen2.5-0.5B compatible SAFE70 LoRA only'
  qwen3_0p6b_training='NOT_STARTED_BY_THIS_SCRIPT'
  s03_writes='NOT_ENABLED'
  original_weights_removed=0
  autonomous_patch='CANDIDATE_STAGING_ONLY'
}
$run | ConvertTo-Json -Depth 5 | Set-Content -Path $startReceipt -Encoding UTF8

Write-Host 'NOX PRIME V8 | starting one source-pinned live chat + M0-M7 candidates + SOUL' -ForegroundColor Cyan
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $source 'NOX_PRIME_LIVE_V6_BOOT.ps1') -SourceSha $SourceSha
if($LASTEXITCODE -ne 0){
    $run.status='LIVE_BOOT_HOLD'
    $run | ConvertTo-Json -Depth 5 | Set-Content $startReceipt -Encoding UTF8
    throw 'NOX PRIME LIVE BOOT HOLD; see exact tests/health above'
}
$run.status='LIVE_STARTED_AUDITING'
$run | ConvertTo-Json -Depth 5 | Set-Content $startReceipt -Encoding UTF8
Write-Host 'NOX PRIME: live chat opened. FORGE self-edit now routes directly from your messages.' -ForegroundColor Green

Write-Host 'NOX PRIME: auditing original models, LoRA checkpoints, verified SOUL and exact duplicates' -ForegroundColor Cyan
& $python -u (Join-Path $source 'nox_prime_weight_audit_v1.py') --root $root
if($LASTEXITCODE -ne 0){
    $run.status='MODEL_AUDIT_HOLD'
    $run | ConvertTo-Json -Depth 5 | Set-Content $startReceipt -Encoding UTF8
    throw 'NOX MODEL AUDIT HOLD; live chat remains, training not started'
}
$run.status='LIVE_AUDIT_COMPLETE'
$run | ConvertTo-Json -Depth 5 | Set-Content $startReceipt -Encoding UTF8
Write-Host 'NOX AUDIT: original weights, adapter and S03 untouched. No deletion automatically.' -ForegroundColor Yellow

if($SkipTraining){
    $run.status='LIVE_READY_TRAINING_SKIPPED'
    $run | ConvertTo-Json -Depth 5 | Set-Content $startReceipt -Encoding UTF8
    exit 0
}

# V7 includes the genuine sequential Qwen teacher/compatible-student
# curriculum, SAFE70 admission and checkpoint. Run ONCE, in foreground.
# VRAM, missing sensors and prior trainer are hard gates, never bypassed.
Write-Host 'NOX PRIME: starting source-hashed teacher distillation + SAFE70 DirectML student' -ForegroundColor Cyan
$run.status='SUPERVISED_STUDENT_TRAINING'
$run | ConvertTo-Json -Depth 5 | Set-Content $startReceipt -Encoding UTF8
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $source 'NOX_PRIME_DISTILL_RUN_V7.ps1') -SourceSha $SourceSha -SkipBoot
$rc=$LASTEXITCODE
if($rc -ne 0){
    $run.status='SUPERVISED_TRAINING_HOLD'
    $run | ConvertTo-Json -Depth 5 | Set-Content $startReceipt -Encoding UTF8
    throw "NOX SUPERVISED TRAINING HOLD RC=$rc; previous checkpoint remains"
}
$run.status='STUDENT_CANDIDATE_TRAINED_EVALUATION_REQUIRED'
$run.completed_utc=(Get-Date).ToUniversalTime().ToString('o')
$run | ConvertTo-Json -Depth 5 | Set-Content $startReceipt -Encoding UTF8
Write-Host 'NOX PRIME: student weights stage finished. Next: independent holdout benchmark before serving/retiring teachers.' -ForegroundColor Green
