# NOX HELION PRIME 9B — CPU full loss + AMD DirectML LoRA gradients (experimental)
# WARNING: Base 19.3 GB weights and existing NOX/S03 are never edited.
# Exits HOLD instead of pretending to train when memory/backend is unsupported.
$ErrorActionPreference = 'Stop'
$prime = 'C:\NOX_HELION\NOX_NEW\brain\prime'
$gpu = Join-Path $prime 'directml-venv\Scripts\python.exe'
$cpuDir = Join-Path $prime 'forge9b\cpu-venv'
$cpu = Join-Path $cpuDir 'Scripts\python.exe'
$script = Join-Path $prime 'forge9b\NOX_9B_DUAL_RUNTIME_FORGE.py'
$report = Join-Path $prime 'forge9b\NOX_9B_GPU_PROGRESS.html'

if (!(Test-Path $gpu)) { throw 'HOLD: existing NOX DirectML Python missing; no changes made' }
$os = Get-CimInstance Win32_OperatingSystem
$ramTotal = [double]$os.TotalVisibleMemorySize / 1024 / 1024
$ramAvailable = [double]$os.FreePhysicalMemory / 1024 / 1024
if ($ramTotal -lt 32 -or $ramAvailable -lt 25) {
    throw ('HOLD: CPU Qwen3.5-9B backbone needs >=32 GiB RAM and >=25 GiB free. Total {0:N1} GiB; available {1:N1} GiB.' -f $ramTotal,$ramAvailable)
}

& $gpu -c 'import torch,torch_directml,numpy,safetensors; d=torch_directml.device(); x=torch.tensor([2.0],device=d,requires_grad=True); (x*x).sum().backward(); assert x.grad is not None; print("NOX DML GRADIENT PASS",d)'
if ($LASTEXITCODE -ne 0) { throw 'HOLD: existing DirectML training backend failed' }

if (!(Test-Path $cpu)) {
    $base = (& $gpu -c 'import sys; print(sys.base_prefix)' | Select-Object -Last 1).Trim()
    $basePy = Join-Path $base 'python.exe'
    if (!(Test-Path $basePy)) { throw 'HOLD: unable to locate original Python for isolated CPU environment' }
    & $basePy -m venv $cpuDir
    if ($LASTEXITCODE -ne 0) { throw 'HOLD: isolated CPU venv creation failed' }
}
$ready = $false
& $cpu -c 'import torch,transformers,accelerate,psutil,safetensors; from packaging.version import Version; assert Version(torch.__version__.split("+")[0])>=Version("2.6"); assert Version(transformers.__version__)>=Version("5.22"); print("CPU BACKBONE ENVIRONMENT PASS")'
if ($LASTEXITCODE -eq 0) {$ready=$true}
if (!$ready) {
    Write-Host 'Installing modern CPU Qwen3.5 runtime in isolated environment (existing DirectML venv untouched)...' -ForegroundColor Cyan
    & $cpu -m pip install --disable-pip-version-check 'torch==2.6.0' --index-url 'https://download.pytorch.org/whl/cpu'
    if ($LASTEXITCODE -ne 0) { throw 'HOLD: CPU torch installation failed' }
    & $cpu -m pip install --disable-pip-version-check 'transformers==5.22.2' 'accelerate>=1.0' 'psutil>=5.9' 'safetensors>=0.6' 'numpy>=1.26'
    if ($LASTEXITCODE -ne 0) { throw 'HOLD: Qwen3.5 CPU dependencies failed' }
}
& $cpu -c 'import torch,transformers,accelerate,psutil,safetensors; from transformers import Qwen3_5ForConditionalGeneration; from packaging.version import Version; assert Version(torch.__version__.split("+")[0])>=Version("2.6"); print("NOX CPU QWEN3.5 CLASS PASS")'
if ($LASTEXITCODE -ne 0) {throw 'HOLD: Qwen3.5 CPU model class unavailable'}

$null = New-Item -ItemType Directory -Force (Split-Path $script)
$srcURL = 'https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/cd42cd6a65f4f4704cdd23cba32c3581f90e4b0f/coordination/prime_genesis/NOX_9B_DUAL_RUNTIME_FORGE.py'
$expected = 'eb8f9259063509848cb250e640026f0ed24f3ea5576b4e24310af71013072376'
$temp = "$script.download"
Invoke-WebRequest -Uri $srcURL -OutFile $temp -TimeoutSec 120 -UseBasicParsing
$actual = (Get-FileHash -LiteralPath $temp -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) { throw "NOX SOURCE INTEGRITY HOLD: $actual" }
Move-Item $temp $script -Force
& $cpu -m py_compile $script
if ($LASTEXITCODE -ne 0) { throw 'HOLD: trainer source compilation failed' }

Write-Host 'NOX PRIME FORGE: 8 segmented stages / CPU 9B forward-backward / DirectML GPU adapter updates' -ForegroundColor Cyan
Write-Host 'Original 19.3GB model: IMMUTABLE; old checkpoint/S03: PRESERVED; SAFE70: ACTIVE'
& $cpu -u $script --init-report
if (Test-Path $report) { Start-Process $report }

& $cpu -u $script --cpu-python $cpu --gpu-python $gpu --stages 8
if ($LASTEXITCODE -ne 0) { throw 'NOX 9B TRAINING HOLD: check error above. Old weights preserved.' }
if (Test-Path $report) { Start-Process $report }
Write-Host 'NOX 9B EXPERIMENTAL LORA CYCLE FINISHED (not yet merged/promoted)' -ForegroundColor Green