$ErrorActionPreference='Stop'
$key=Join-Path $env:USERPROFILE '.ssh\nox_runpod_ed25519'
if(!(Test-Path -LiteralPath $key -PathType Leaf)){throw 'NOX SSH key missing'}
$url='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/3a3fdbbed16052521e87dc9396f0bc305c2e6eb1/nox_runpod/stage0/start_detached_embryo.sh'
$file=Join-Path $env:TEMP 'NOX_Genesis_Mega_Stage0.sh'
Invoke-WebRequest -Uri $url -OutFile $file -ErrorAction Stop
if(!(Test-Path -LiteralPath $file -PathType Leaf)){throw 'Launcher download failed'}
$body=[IO.File]::ReadAllText($file).Replace([string][char]13+[string][char]10,[string][char]10)
Write-Host 'NOX GENESIS Stage 0: detached teacher-to-Embryo training on RTX A5000' -ForegroundColor Cyan
$body | & ssh -i $key -p 22189 -o BatchMode=yes -o ConnectTimeout=20 -o StrictHostKeyChecking=accept-new root@69.30.85.251 'bash -s'
if($LASTEXITCODE -ne 0){throw 'NOX Genesis launch failed; RTX A5000 may still be billing. Check RunPod Pods.'}
Write-Host 'Two-pass NOX Embryo training launch requested. Windows can disconnect. Only checkpoints and validation receipts prove actual learning.' -ForegroundColor Green
