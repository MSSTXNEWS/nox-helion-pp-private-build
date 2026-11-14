# NOX PRIME: Stage1 download, ONE trainable Qwen3-0.6B + memory/affect/voice.
# Windows PowerShell 5.1. No GUI/engine windows. No weights deleted.
# Runs only the pinned source archive. Does NOT start GPU training.
param(
 [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{40}$')][string]$SourceSha,
 [string]$Root='C:\NOX_HELION\NOX_NEW'
)
$ErrorActionPreference='Stop'
$env:PYTHONUTF8='1'
$env:PYTHONIOENCODING='utf-8'
$env:HF_HUB_DISABLE_TELEMETRY='1'
$source=Split-Path -Parent $MyInvocation.MyCommand.Path
$repo=Join-Path $Root 'brain\source\repo'
$originalPy=Join-Path $env:USERPROFILE 'NOX_EXPRESS_AI\NOX_TRAINING\train-venv\Scripts\python.exe'
$venv=Join-Path $Root 'brain\downloads\stage1-downloader-venv'
$downloadPy=Join-Path $venv 'Scripts\python.exe'
$script=Join-Path $source 'nox_prime_stage1_download_all_v1.py'
$stageFiles=@(
 'nox_prime_stage1_download_all_v1.py',
 'nox_prime_download_five_v1.py',
 'nox_prime_progress_v1.py',
 'nox_prime_soul_stage1_train.py',
 'download_nox_voice_max.py',
 'NOX_VOICE_MAX_MODELS_MANIFEST_V1.json'
)
if (!(Test-Path "$repo\.git")) { throw 'EXISTING_NOX_GIT_REPO_MISSING' }
if (!(Test-Path "$Root\brain")) { throw 'EXISTING_NOX_BRAIN_MISSING' }
if (!(Test-Path $originalPy)) { throw "EXISTING_NOX_PYTHON_MISSING $originalPy" }
foreach ($file in $stageFiles) {
    if (!(Test-Path (Join-Path $source $file))) { throw "MISSING_PINNED_SOURCE $file" }
}
$actualSHA=(& git -C $repo rev-parse $SourceSha).Trim()
if ($LASTEXITCODE -ne 0 -or $actualSHA -ne $SourceSha) {
    throw 'SOURCE_SHA_MISMATCH'
}
$env:HF_HOME=Join-Path $Root 'brain\downloads\huggingface_cache'
$env:HF_HUB_CACHE=Join-Path $env:HF_HOME 'hub'
$env:TEMP=Join-Path $Root 'brain\downloads\tmp'
$env:TMP=$env:TEMP
foreach ($folder in @($env:HF_HOME,$env:HF_HUB_CACHE,$env:TEMP)) {
    New-Item -Force -ItemType Directory $folder | Out-Null
}
Write-Host "NOX STAGE1: pinned source $SourceSha" -ForegroundColor Cyan
Write-Host 'Priority: single compatible Qwen3-0.6B, affect, memory, RU/ES speech and voice'
Write-Host 'No existing checkpoint, installed model, S03 record, or engine is deleted.'
if (!(Test-Path $downloadPy)) {
    & $originalPy -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw 'STAGE1_VENV_CREATION_HOLD' }
}
& $downloadPy -m pip install --disable-pip-version-check --only-binary=:all: 'huggingface_hub==0.36.0'
if ($LASTEXITCODE -ne 0) { throw 'HUGGINGFACE_DOWNLOAD_DEPENDENCY_HOLD' }
$pythonSources=@($stageFiles | Where-Object {$_ -like '*.py'} | ForEach-Object {Join-Path $source $_})
& $downloadPy -m py_compile @pythonSources
if ($LASTEXITCODE -ne 0) { throw 'STAGE1_PYTHON_SOURCE_SYNTAX_HOLD' }
Write-Host 'NOX STAGE1: downloading verified candidates into own brain folders...' -ForegroundColor Cyan
& $downloadPy -u $script --root $Root --source $source
if ($LASTEXITCODE -ne 0) {
    throw 'NOX_STAGE1_DOWNLOAD_HOLD: look at real events in existing FORGE dashboard'
}
Write-Host 'NOX STAGE1 DOWNLOADS COMPLETE: see brain\telemetry\stage1_download_summary.json' -ForegroundColor Green
Write-Host 'Training is a separate SAFE70 phase; no unsupported GPU operations were started.' -ForegroundColor Yellow
