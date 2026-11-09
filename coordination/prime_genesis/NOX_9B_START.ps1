# NOX HELION: one command, genuine language-loss GPU adapter on inherited Qwen3.5-9B.
# No original 9B weights, embryo checkpoint, S03, or source chats are deleted.
# Scope: POST-LANGUAGE-MODEL OUTPUT ADAPTER, not full 9B matrix training.
$ErrorActionPreference='Stop'
$prime='C:\NOX_HELION\NOX_NEW\brain\prime'
$model=Join-Path $prime 'models\NOX_PRIME_9B_INHERITED'
$gpu=Join-Path $prime 'directml-venv\Scripts\python.exe'
$dir=Join-Path $prime 'forge9b\real_language_adapter'
$cpu=Join-Path $dir 'cpu-venv\Scripts\python.exe'
$script=Join-Path $dir 'NOX_9B_REAL_LANGUAGE_ADAPTER.py'
if (!(Test-Path $model)) {throw 'HOLD: inherited 9B full weights missing'}
if (!(Test-Path (Join-Path $prime 'NOX_PRIME_9B_MANIFEST.json'))) {throw 'HOLD: original full weights manifest missing'}
if (!(Test-Path $gpu)) {throw 'HOLD: existing DirectML training Python missing'}
$drive=Get-PSDrive -Name C
if ($drive.Free -lt 25GB) {throw ('HOLD: CPU/DISK offload needs 25GB free SSD. Available: {0:N1} GB' -f ($drive.Free/1GB))}
& $gpu -c 'import torch,torch_directml,numpy,safetensors; d=torch_directml.device(); x=torch.tensor([2.],device=d,requires_grad=True); (x*x).sum().backward(); assert x.grad is not None; print("NOX RX6650M DIRECTML: AVAILABLE")'
if ($LASTEXITCODE -ne 0) {throw 'HOLD: existing DirectML GPU backend unavailable'}
New-Item -ItemType Directory -Force $dir | Out-Null
if (!(Test-Path $cpu)) {
  $base=(& $gpu -c 'import sys;print(sys.base_prefix)' | Select-Object -Last 1).Trim()
  $basepy=Join-Path $base 'python.exe'
  if (!(Test-Path $basepy)) {throw 'HOLD: cannot locate base Python for separate CPU environment'}
  & $basepy -m venv (Join-Path $dir 'cpu-venv')
  if ($LASTEXITCODE -ne 0) {throw 'HOLD: CPU Python environment creation failed'}
}
& $cpu -c 'import torch,transformers,accelerate,safetensors,numpy;from transformers import Qwen3_5ForConditionalGeneration;from packaging.version import Version;assert Version(torch.__version__.split("+")[0])>=Version("2.6")'
if ($LASTEXITCODE -ne 0) {
  Write-Host 'NOX: installing CPU-only Qwen3.5 runtime (old GPU environment untouched)' -ForegroundColor Cyan
  & $cpu -m pip install --disable-pip-version-check 'torch>=2.6,<3' --index-url 'https://download.pytorch.org/whl/cpu'
  if ($LASTEXITCODE -ne 0) {throw 'HOLD: CPU PyTorch installation failed'}
  & $cpu -m pip install --disable-pip-version-check 'transformers>=5.22,<6' 'accelerate>=1' 'safetensors>=0.6' 'numpy>=1.26' 'packaging>=24'
  if ($LASTEXITCODE -ne 0) {throw 'HOLD: CPU Qwen3.5 runtime installation failed'}
}
& $cpu -c 'from transformers import Qwen3_5ForConditionalGeneration;print("NOX QWEN3.5 CPU LOAD SUPPORT: AVAILABLE")'
if ($LASTEXITCODE -ne 0) {throw 'HOLD: Qwen3.5 CPU Transformers class not available'}
# This URL and checksum are versioned at a single immutable GitHub commit.
$commit='e5bb02eb46f5bcfeae8d0431bfcd2166cf7b56c3'
$expected='211a6b1ecb53dcf5682e7617e4c1b57d3ae4477d34478a0da3c6f868ba994663'
$url="https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/$commit/coordination/prime_genesis/NOX_9B_REAL_LANGUAGE_ADAPTER.py"
$temp="$script.download"
Invoke-WebRequest -Uri $url -OutFile $temp -TimeoutSec 120 -UseBasicParsing
$actual=(Get-FileHash -LiteralPath $temp -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actual -ne $expected) {throw "HOLD: trainer source SHA-256 mismatch: $actual"}
Move-Item -LiteralPath $temp -Destination $script -Force
& $cpu -m py_compile $script
if ($LASTEXITCODE -ne 0) {throw 'HOLD: trainer code syntax failed'}
Write-Host 'NOX: real supervised 9B hidden-state learning -> DirectML rank4 adapter' -ForegroundColor Cyan
Write-Host 'SAFE70 active. Original 9B BF16 weights and S03 immutable.'
Write-Host 'This trains an output adapter, NOT all 9B base weights.'
& $gpu -u $script --cpu-python $cpu --gpu-python $gpu
if ($LASTEXITCODE -ne 0) {throw 'NOX REAL LEARNING HOLD: previous model and checkpoints preserved'}
Write-Host 'NOX: 9B LANGUAGE ADAPTER TRAINED. Inspect experimental receipt before promotion.' -ForegroundColor Green