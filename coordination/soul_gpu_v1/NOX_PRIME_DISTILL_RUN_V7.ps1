# NOX PRIME V7, in-foreground teaching and compatible 0.5B training.
# Source only uses existing OneHost/S03. No invented "absorbed 19 weights".
param([Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{40}$')][string]$SourceSha)
$ErrorActionPreference='Stop'
$root='C:\NOX_HELION\NOX_NEW'
$repo="$root\brain\source\repo"
$source=Split-Path -Parent $MyInvocation.MyCommand.Path
$py=Join-Path $env:USERPROFILE 'NOX_EXPRESS_AI\NOX_TRAINING\train-venv\Scripts\python.exe'
if (!(Test-Path "$repo\.git") -or !(Test-Path "$root\brain") -or !(Test-Path $py)) {
    throw 'NOX EXISTING SOURCE, BRAIN, OR PYTHON NOT FOUND'
}
$required=@('NOX_PRIME_LIVE_V6_BOOT.ps1','nox_prime_progress_v1.py',
'nox_prime_distill_v1.py','nox_prime_absorption_registry_v1.py','nox_prime_absorb_text_v2.py',
'nox_gpu_worm_safe70_v1.py','nox_gpu_target_11120.py','nox_safe70_thermal_guard_v1.py','forge_live_server_v6.py')
foreach ($f in $required) {
    if (!(Test-Path (Join-Path $source $f))) { throw "MISSING_NOX_COMPONENT: $f" }
}
function NoxEvent($phase,$status,$detail) {
    & $py -u (Join-Path $source 'nox_prime_progress_v1.py') --root $root --phase $phase --status $status --detail $detail
    if($LASTEXITCODE -ne 0){throw 'NOX_EVENT_JOURNAL_FAILED'}
}
function AssertNoTraining {
    $busy=@(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -match '^python(?:w)?[.]exe$' -and
        $_.CommandLine -match 'nox_gpu_(?:target_11120|worm_safe70_v1|safe65_v2|10000)[.]py|train_directml_lora[.]py|nox_prime_soul_stage1_train[.]py'
    })
    if($busy.Count){
        NoxEvent 'HOLD' 'HOLD' 'Prior GPU trainer still running; NO second trainer started'
        $busy | Select-Object ProcessId,CommandLine | Format-List
        throw 'OLD_GPU_TRAINER_RUNNING'
    }
}
NoxEvent 'DISCOVER' 'START' 'NOX PRIME v7 loaded from exact source archive'
AssertNoTraining
if ([IO.DriveInfo]::new([IO.Path]::GetPathRoot($root)).AvailableFreeSpace -lt 60GB) {
    NoxEvent 'HOLD' 'HOLD' 'Less than 60GB free disk; preserving checkpoints'
    throw 'NOX_DISK_RESERVE_HOLD'
}
NoxEvent 'INTEGRATE' 'START' 'Launching existing NOX V6 with real memory endpoints and D02 dashboard'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $source 'NOX_PRIME_LIVE_V6_BOOT.ps1') -SourceSha $SourceSha
if($LASTEXITCODE -ne 0){
    NoxEvent 'INTEGRATE' 'HOLD' 'Unified NOX runtime did not start; training not launched'
    throw 'NOX_PRIME_BOOT_HOLD'
}
NoxEvent 'INTEGRATE' 'SAVED' 'Existing local NOX is online; native S03 writes remain owner-gated'
$ollama=Get-Command ollama -ErrorAction SilentlyContinue
if($null -eq $ollama){throw 'OLLAMA_CLI_MISSING'}
NoxEvent 'DOWNLOAD' 'START' 'Checking installed local Qwen teacher and embedding'
$catalog=@(& ollama list)
if($LASTEXITCODE -ne 0){throw 'OLLAMA_LIST_HOLD'}
if(@($catalog | Where-Object {$_ -match '^qwen3-embedding:0[.]6b\s'}).Count -eq 0){
    if([IO.DriveInfo]::new([IO.Path]::GetPathRoot($root)).AvailableFreeSpace -lt 63GB){
        NoxEvent 'DOWNLOAD' 'HOLD' 'Embedding would violate 60GB disk reserve'
        throw 'NOX_EMBEDDING_SPACE_HOLD'
    }
    NoxEvent 'DOWNLOAD' 'RUNNING' 'Downloading missing official embedding model'
    & ollama pull qwen3-embedding:0.6b
    if($LASTEXITCODE -ne 0){
        NoxEvent 'DOWNLOAD' 'HOLD' 'Embedding pull failed, original models preserved'
        throw 'EMBEDDING_PULL_HOLD'
    }
    NoxEvent 'DOWNLOAD' 'SAVED' 'Embedding downloaded for NOX semantic retrieval'
}else{
    NoxEvent 'DOWNLOAD' 'SAVED' 'Existing Qwen embedding reused without duplicate download'
}
if(@($catalog | Where-Object {$_ -match '^qwen3:8b\s'}).Count -eq 0){
    NoxEvent 'DOWNLOAD' 'HOLD' 'Qwen3:8B primary teacher not found'
    throw 'NOX_PRIMARY_MODEL_NOT_INSTALLED'
}
AssertNoTraining
# Inventory ALL installed models; pilot transfer of actual LANGUAGE/CODE skills.
# Media, audio, embeddings, incompatible architectures stay in their own tracks.
NoxEvent 'DISCOVER' 'RUNNING' 'Inventorying all installed donor weights with exact model digests'
& $py -u (Join-Path $source 'nox_prime_absorption_registry_v1.py') --root $root
if($LASTEXITCODE -ne 0){
    NoxEvent 'DISCOVER' 'HOLD' 'Installed donor model inventory incomplete'
    throw 'NOX_DONOR_REGISTRY_HOLD'
}
NoxEvent 'TEACHER_DISTILL' 'START' 'Sequentially sampling all compatible local text and coding teachers'
& $py -u (Join-Path $source 'nox_prime_absorb_text_v2.py') --root $root --questions-per-model 3 --max-models 40
if($LASTEXITCODE -ne 0){
    NoxEvent 'TEACHER_DISTILL' 'HOLD' 'Some donor models cannot yet be sampled; no weights deleted'
    throw 'NOX_ALL_TEACHERS_PILOT_HOLD'
}
NoxEvent 'TEACHER_DISTILL' 'SAVED' 'Model-specific donor candidate datasets captured; media/voice kept as specialists'
AssertNoTraining
NoxEvent 'DATASET_PREP' 'START' 'Preparing verified Qwen student curriculum for real DirectML learning'
& $py -u (Join-Path $source 'nox_prime_distill_v1.py') --root $root --max-tasks 24
if($LASTEXITCODE -ne 0){
    NoxEvent 'DATASET_PREP' 'HOLD' 'Local teacher distillation dataset was not completed'
    throw 'NOX_TEACHER_DISTILL_HOLD'
}
NoxEvent 'DATASET_PREP' 'SAVED' 'Local teacher training dataset saved and SHA-256 verified'
AssertNoTraining
# Release teacher VRAM; the light local NOX server stays online and reports
# the temporary GPU limit rather than loading a competing heavy model.
NoxEvent 'GPU_TRAIN' 'RUNNING' 'Releasing teacher GPU model for single SAFE70 learner'
& ollama stop qwen3:8b 2>$null | Out-Null
if (@($catalog | Where-Object {$_ -match '^qwen2[.]5-coder:7b\s'}).Count -gt 0) {
    & ollama stop qwen2.5-coder:7b 2>$null | Out-Null
}
Start-Sleep -Seconds 2
try {
    $loaded = Invoke-RestMethod 'http://127.0.0.1:11434/api/ps' -TimeoutSec 8
    $inGpu = @($loaded.models | Where-Object { $_.size_vram -gt 0 })
    if ($inGpu.Count -gt 0) {
        NoxEvent 'GPU_TRAIN' 'HOLD' 'Another Ollama GPU model still resident; leave it untouched'
        throw 'GPU_VRAM_LEASE_HOLD'
    }
}catch [System.Net.WebException] {
    NoxEvent 'GPU_TRAIN' 'HOLD' 'Cannot verify GPU model residency before SAFE70'
    throw
}
$env:NOX_USE_TEACHER_DISTILL_V1='1'
NoxEvent 'GPU_TRAIN' 'START' 'Actual SAFE70 DirectML LoRA training on distilled local teacher data'
try {
    & $py -u (Join-Path $source 'nox_gpu_worm_safe70_v1.py')
    $rc=$LASTEXITCODE
    if($rc -ne 0){
        NoxEvent 'GPU_TRAIN' 'HOLD' 'GPU trainer halted; previously saved LoRA checkpoint preserved'
        throw "NOX_GPU_TRAINING_HOLD_RC_$rc"
    }
    NoxEvent 'GPU_TRAIN' 'SAVED' 'Compatible student step goal reached; held-out evaluation still pending'
}finally{
    Remove-Item Env:NOX_USE_TEACHER_DISTILL_V1 -ErrorAction SilentlyContinue
}
NoxEvent 'EVALUATE' 'HOLD' 'Distilled student remains unpromoted until independent benchmark'
Write-Host 'NOX CORE LIVE. Existing D02 dashboard shows actual teacher/model/GPU-step progress.' -ForegroundColor Green
Write-Host 'Distilled 0.5B student is separate; incompatible teacher weights not tensor-merged.' -ForegroundColor Yellow
