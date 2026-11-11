# NOX PRIME: direct installation and a 3-minute autonomous update loop.
$ErrorActionPreference='Stop'
$key=Join-Path $env:USERPROFILE '.ssh\nox_runpod_ed25519'
if(!(Test-Path $key)){throw 'NOX_SSH_KEY_MISSING'}
$branch='feature/nox-prime-v3-teachers-progress-20261110'
$url='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/'+$branch+'/nox_runpod/v3/nox_mega1_tick.sh'
$nodes=@(@{Name='A5000';Host='69.30.85.188';Port=22199},@{Name='A40';Host='69.30.85.193';Port=22088})
$results=@()
foreach($n in $nodes){
 $node=$n.Name
 $target='/workspace/nox/dispatcher/nox_v3/bin/nox_mega1_tick.sh'
 $cron='*/3 * * * * bash '+$target+' '+$node+' >> /workspace/nox/logs/NOX_MEGA1_TICK_'+$node+'.log 2>&1'
 $reboot='@reboot bash '+$target+' '+$node+' >> /workspace/nox/logs/NOX_MEGA1_TICK_'+$node+'.log 2>&1'
 $remote='set -Eeuo pipefail; mkdir -p /workspace/nox/dispatcher/nox_v3/bin /workspace/nox/logs; curl -fsSL --retry 3 '+[char]39+$url+[char]39+' -o '+$target+'.new; bash -n '+$target+'.new; mv -f '+$target+'.new '+$target+'; bash '+$target+' '+$node+'; if command -v crontab >/dev/null; then { crontab -l 2>/dev/null || true; } | grep -v -F nox_mega1_tick.sh > /tmp/nox_v3_cron_'+$node+'.txt || true; echo '+[char]39+$cron+[char]39+' >> /tmp/nox_v3_cron_'+$node+'.txt; echo '+[char]39+$reboot+[char]39+' >> /tmp/nox_v3_cron_'+$node+'.txt; crontab /tmp/nox_v3_cron_'+$node+'.txt; echo POD_CRON_3MIN_ENABLED; else echo POD_CRON_MISSING_WINDOWS_BACKUP_USED; fi'
 Write-Host ('NOX_MEGA1_INSTALL '+$node) -ForegroundColor Cyan
 & ssh.exe -T -i $key -p $n.Port -o BatchMode=yes -o ConnectTimeout=20 ('root@'+$n.Host) $remote
 $results += [pscustomobject]@{Node=$node;Exit=$LASTEXITCODE}
 if($LASTEXITCODE -ne 0){Write-Warning ('HOLD_POD_INSTALL_'+$node)}
}
$dir='C:\NOX_HELION\NOX_NEW\scripts'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
$fallback=Join-Path $dir 'nox_mega1_tick_windows.ps1'
$content=@'
$ErrorActionPreference='Continue'
$key=Join-Path $env:USERPROFILE '.ssh\nox_runpod_ed25519'
if(!(Test-Path $key)){throw 'NOX_SSH_KEY_MISSING'}
foreach($n in @(@{Name='A5000';Host='69.30.85.188';Port=22199},@{Name='A40';Host='69.30.85.193';Port=22088})){
 $cmd='bash /workspace/nox/dispatcher/nox_v3/bin/nox_mega1_tick.sh '+$n.Name
 & ssh.exe -T -i $key -p $n.Port -o BatchMode=yes -o ConnectTimeout=12 ('root@'+$n.Host) $cmd
 if($LASTEXITCODE -ne 0){Write-Warning ('HOLD_REMOTE_UPDATE_'+$n.Name)}
}
'@
Set-Content -LiteralPath $fallback -Value $content -Encoding UTF8
$task='NOX-MEGA1-Autoupdate'
$tr='powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$fallback+'"'
& schtasks.exe /Create /F /SC MINUTE /MO 3 /TN $task /TR $tr
if($LASTEXITCODE -ne 0){throw 'HOLD_SCHEDULE_FAILED'}
& schtasks.exe /Run /TN $task
Write-Host 'NOX_MEGA1_AUTOUPDATE_EVERY_3MIN_ENABLED' -ForegroundColor Green
$results | Format-Table -AutoSize
