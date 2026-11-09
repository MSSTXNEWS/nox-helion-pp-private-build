$ErrorActionPreference='Stop'
$base='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/feature/nox-runpod-trainer-stage0/nox_runpod/stage0/'
$key=Join-Path $env:USERPROFILE '.ssh\nox_runpod_ed25519'
if(!(Test-Path -LiteralPath $key -PathType Leaf)){throw 'NOX SSH private key missing'}
Write-Host 'NOX Stage 0: resume 9B, launch first teacher pass for original Embryo V1.'
$resume=Join-Path $env:TEMP 'NOX_Resume_9B.ps1'
Invoke-WebRequest ($base+'resume_9b_to_a5000.ps1') -OutFile $resume -ErrorAction Stop
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $resume
if($LASTEXITCODE -ne 0){throw '9B cloud transfer incomplete or another transfer active. Teacher not started.'}
$launcher=Join-Path $env:TEMP 'NOX_Embryo_Genesis.sh'
Invoke-WebRequest ($base+'launch_embryo_teacher.sh') -OutFile $launcher -ErrorAction Stop
$body=[IO.File]::ReadAllText($launcher)
Write-Host 'Running verified 9B teacher generation on RTX A5000' -ForegroundColor Cyan
$body | & ssh -i $key -p 22189 -o BatchMode=yes -o ConnectTimeout=20 -o StrictHostKeyChecking=accept-new root@69.30.85.251 'bash -s'
if($LASTEXITCODE -ne 0){throw 'Teacher process failed; examine /workspace/nox/logs/embryo_9b_genesis.log'}
Write-Host 'TEACHER_DATA_READY. Embryo weights not yet trained; no birth recorded.'
