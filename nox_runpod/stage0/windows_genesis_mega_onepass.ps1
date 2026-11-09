$ErrorActionPreference='Stop'
$key=Join-Path $env:USERPROFILE '.ssh\nox_runpod_ed25519'
if(!(Test-Path -LiteralPath $key -PathType Leaf)){throw 'NOX SSH key missing'}
$scriptUrl='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/ccba2e8bcd015be1cac3ff7156e9d4916ca2c150/nox_runpod/stage0/start_detached_embryo.sh'
Write-Host 'NOX GENESIS: launch/resume detached three-pass trainer on A5000; no Windows shell piping' -ForegroundColor Cyan
# Server downloads and executes the script on Linux itself. Prevents PowerShell CRLF injection.
$cmd="curl -fsSL --retry 3 --connect-timeout 15 '$scriptUrl' | bash"
& ssh -i $key -p 22189 -o BatchMode=yes -o ConnectTimeout=20 -o StrictHostKeyChecking=accept-new root@69.30.85.251 $cmd
if($LASTEXITCODE -ne 0){throw 'NOX Genesis launcher failed; RunPod may still be billing.'}
Write-Host 'Remote detached process requested. Checking most recent training log...' -ForegroundColor Cyan
& ssh -i $key -p 22189 -o BatchMode=yes -o ConnectTimeout=20 root@69.30.85.251 'tail -n 30 /workspace/nox/logs/nox_embryo_unattended.log 2>/dev/null || true'
Write-Host 'Only step logs and saved checkpoint confirm training; Windows may disconnect once process remains alive.' -ForegroundColor Green
