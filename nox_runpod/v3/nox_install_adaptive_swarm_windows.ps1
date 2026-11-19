# NOX V3: install adaptive worker swarm without restarting full model training.
$ErrorActionPreference='Stop'
$dir='C:\NOX_HELION\NOX_NEW\scripts'
$branch='feature/nox-prime-v3-teachers-progress-20261110'
$base='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/'+$branch+'/nox_runpod/v3'
$key=Join-Path $env:USERPROFILE '.ssh\nox_runpod_ed25519'
if(!(Test-Path $key)){throw 'NOX_SSH_KEY_MISSING'}
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$swarmScript=Join-Path $dir 'nox_v3_swarm_tick.ps1'
$nodeCode=@'
$ErrorActionPreference='Continue'
$key=Join-Path $env:USERPROFILE '.ssh\nox_runpod_ed25519'
$nodes=@(@{Name='A40';Host='69.30.85.193';Port='22088'},@{Name='A5000';Host='69.30.85.188';Port='22199'})
$branch='feature/nox-prime-v3-teachers-progress-20261110'
$url='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/'+$branch+'/nox_runpod/v3/nox_adaptive_swarm.py'
foreach($n in $nodes){
 $script='/workspace/nox/dispatcher/nox_v3/bin/nox_adaptive_swarm.py'
 $remote='mkdir -p /workspace/nox/dispatcher/nox_v3/bin && curl -fsSL --retry 2 '+$url+' -o '+$script+'.new && python3 -m py_compile '+$script+'.new && mv '+$script+'.new '+$script+' && python3 '+$script+' --node '+$n.Name
 & ssh.exe -T -i $key -p $n.Port -o BatchMode=yes -o ConnectTimeout=15 ('root@'+$n.Host) $remote
 if($LASTEXITCODE -ne 0){Write-Warning ('NOX_SWARM_HOLD_'+$n.Name)}
}
'@
Set-Content -LiteralPath $swarmScript -Value $nodeCode -Encoding UTF8
$task='NOX-V3-Adaptive-Swarm'
$run='powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$swarmScript+'"'
& schtasks.exe /Create /F /SC MINUTE /MO 3 /TN $task /TR $run
if($LASTEXITCODE -ne 0){throw 'HOLD_SWARM_SCHEDULE_FAILED'}
& schtasks.exe /Run /TN $task
if($LASTEXITCODE -ne 0){throw 'HOLD_SWARM_START_FAILED'}
Write-Host 'NOX_ADAPTIVE_SWARM_SCHEDULED_EVERY_3_MINUTES' -ForegroundColor Green
Write-Host ('TASK_SCRIPT='+$swarmScript)
