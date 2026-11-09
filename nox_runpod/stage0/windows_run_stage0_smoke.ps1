$ErrorActionPreference = 'Stop'
$hostName='194.68.245.68'
$port=22102
$key=Join-Path $env:USERPROFILE '.ssh\nox_runpod_ed25519'
$script=Join-Path $env:TEMP 'NOX_stage0_gpu_smoke.sh'
$uri='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/feature/nox-runpod-trainer-stage0/nox_runpod/stage0/remote_stage0_smoke.sh'
if(-not (Test-Path -LiteralPath $key)){throw "Missing SSH key: $key"}
Invoke-WebRequest -Uri $uri -OutFile $script -ErrorAction Stop
Write-Host 'NOX stage0: GPU smoke training on the transferred local weights. Pod must be running.' -ForegroundColor Cyan
Write-Host 'This is NOT teacher distillation, is limited to 2 optimizer steps and 20 minutes, and does not stop the RunPod billing automatically.'
$inputScript=Get-Content -LiteralPath $script -Raw -Encoding UTF8
$inputScript -replace "`r`n","`n" | & ssh -o BatchMode=yes -o ConnectTimeout=12 -o StrictHostKeyChecking=accept-new -i $key -p $port "root@$hostName" 'bash -s'
$exit=$LASTEXITCODE
if($exit -ne 0){Write-Host "NOX smoke failed ($exit). Stop Pod billing in RunPod." -ForegroundColor Red;exit $exit}
Write-Host 'NOX smoke finished. Check remote result; STOP Pod to prevent further billing.' -ForegroundColor Yellow
