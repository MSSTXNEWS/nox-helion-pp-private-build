# NOX PRIME stage-1 new weights/download. ASCII-only PowerShell 5.1 source.
# Never auto-kill the original trainer, overwrite LoRA, S03 or deployed host.
param([switch]$SkipEmbedding,[switch]$SkipVoice)
$ErrorActionPreference="Stop"
$root="C:\NOX_HELION\NOX_NEW"
$here=Split-Path -Parent $MyInvocation.MyCommand.Path
$python=Join-Path $env:USERPROFILE "NOX_EXPRESS_AI\NOX_TRAINING\train-venv\Scripts\python.exe"

if (!(Test-Path "$root\brain")) { throw "Existing NOX brain not found: $root" }
if (!(Test-Path $python)) { throw "Existing NOX training Python environment missing: $python" }
Write-Host "NOX PRIME STAGE1: preflight" -ForegroundColor Cyan

# The owner must stop OLD trainer first. Never kill it from the installer.
$running=@(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^python(?:w)?[.]exe$' -and $_.CommandLine -match 'train_directml_lora[.]py|nox_gpu_(?:target_11120|worm_safe70_v1|safe65_v2|10000)[.]py|nox_prime_soul_stage1_train[.]py'
})
if ($running.Count -gt 0) {
    $running | Select-Object ProcessId,CommandLine | Format-List
    throw "OLD/NEW TRAINING PROCESS STILL RUNNING. Stop it normally before new Stage1. No duplicate worker launched."
}

$names=@("nox_prime_soul_stage1_train.py","test_nox_prime_soul_stage1_train.py")
foreach ($f in $names) {
    if (!(Test-Path (Join-Path $here $f))) { throw "Missing pinned trainer file: $f" }
}
& $python -m py_compile (Join-Path $here "nox_prime_soul_stage1_train.py") (Join-Path $here "test_nox_prime_soul_stage1_train.py")
if ($LASTEXITCODE -ne 0) { throw "Stage1 source syntax failed" }
Push-Location $here
try {
    & $python -m unittest -q test_nox_prime_soul_stage1_train
    if ($LASTEXITCODE -ne 0) { throw "Stage1 no-network unit tests failed" }
}
finally { Pop-Location }

# CPU-first learning, no GPU training until separately verified/approved.
& $python -c "import torch, safetensors; print('NOX training deps:', torch.__version__)"
if ($LASTEXITCODE -ne 0) { throw "Torch and safetensors missing in existing train-venv" }

if (!$SkipEmbedding) {
    $ollama=Get-Command ollama -ErrorAction SilentlyContinue
    if ($null -eq $ollama) {
        Write-Warning "Ollama command missing: embedding download HOLD. CPU new training can proceed."
    }
    else {
        $models=@(& ollama list)
        if ($LASTEXITCODE -ne 0) { throw "Ollama list failed" }
        if ($models -notmatch 'qwen3-embedding:0[.]6b(?:\s|$)') {
            Write-Host "NOX downloading official qwen3-embedding:0.6b" -ForegroundColor Cyan
            & ollama pull qwen3-embedding:0.6b
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "Embedding download failed; preserving existing models and continuing CPU SOUL learning."
            }
        }
        else { Write-Host "Embedding already installed. Reusing verified model tag." -ForegroundColor Green }
    }
}

Write-Host ""
Write-Host "NOX: starting NEW SOUL neural weights training on CPU" -ForegroundColor Cyan
Write-Host "Dataset: official Google GoEmotions, pinned train/dev/test."
Write-Host "Old Qwen2.5 LoRA checkpoints and canonical S03 are read-only to this script." -ForegroundColor Yellow
Write-Host "New model: hashed features + neural MLP6, English emotions research-only."
& $python -u (Join-Path $here "nox_prime_soul_stage1_train.py") --root $root --epochs 2
$trainRC=$LASTEXITCODE
if ($trainRC -ne 0) {
    throw "New SOUL training HOLD rc=$trainRC, see error above; old weights untouched"
}
Write-Host "NOX new training finished; see real holdout results and model weights." -ForegroundColor Green

if (!$SkipVoice) {
    # Download only; does NOT install/execute neural TTS on RX6650M.
    $voicePy=Join-Path $here "download_nox_voice_max.py"
    $voiceManifest=Join-Path $here "NOX_VOICE_MAX_MODELS_MANIFEST_V1.json"
    if (!(Test-Path $voicePy) -or !(Test-Path $voiceManifest)) {
        Write-Warning "VOICE MAX scripts absent; training completed, voices HOLD."
    }
    else {
        $voiceVenv=Join-Path $root "brain\voice\tools-venv"
        $voicePython=Join-Path $voiceVenv "Scripts\python.exe"
        try {
            if (!(Test-Path $voicePython)) {
                & $python -m venv $voiceVenv
                if ($LASTEXITCODE -ne 0) { throw "Voice environment creation failed" }
            }
            & $voicePython -m pip install --disable-pip-version-check "huggingface_hub==0.36.0"
            if ($LASTEXITCODE -ne 0) { throw "Voice dependency install failed" }
            & $voicePython -u $voicePy --group starter --mode models --only qwen3_06_customvoice --execute
            if ($LASTEXITCODE -ne 0) { throw "Voice starter download incomplete" }
        }
        catch {
            Write-Warning ("VOICE MAX HOLD (new training unaffected): " + $_.Exception.Message)
        }
    }
}
Write-Host ""
Write-Host "NOX STAGE1 result: $root\brain\intelligence\soul_stage1" -ForegroundColor Green
Write-Host "New neural weights are candidates until holdout acceptance + OneHost integration."
