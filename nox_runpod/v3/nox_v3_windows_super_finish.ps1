# NOX V3 one-time Windows receiver and save-point cutover scheduler.
$ErrorActionPreference='Stop'
$root='C:\NOX_HELION\NOX_NEW'
$dir=Join-Path $root 'scripts'
$key=Join-Path $env:USERPROFILE '.ssh\nox_runpod_ed25519'
$branch='feature/nox-prime-v3-teachers-progress-20261110'
$base='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/'+$branch+'/nox_runpod/v3'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
if(!(Test-Path $key)){throw 'NOX_SSH_KEY_MISSING'}
foreach($filename in @('nox_windows_v3_receiver.ps1','nox_windows_identity_sync.ps1','nox_windows_v3_cutover_retry.ps1')){
 $url=$base+'/'+$filename
 $dest=Join-Path $dir $filename
 Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile ($dest+'.new')
 if((Get-Item ($dest+'.new')).Length -lt 1000){throw ('HOLD_SMALL_SCRIPT_'+$filename)}
 Move-Item -Force ($dest+'.new') $dest
 Write-Host ('INSTALLED '+$filename)
}
$oldTasks=@('NOX-Verified-Windows-Checkpoint-Sync','NOX-RunPod-Verified-Backup-Clean')
foreach($task in $oldTasks){
 $p=Start-Process -FilePath schtasks.exe -ArgumentList @('/Query','/TN',$task) -NoNewWindow -PassThru -Wait -RedirectStandardOutput (Join-Path $dir 'nox_task_query.txt') -RedirectStandardError (Join-Path $dir 'nox_task_query_err.txt')
 if($p.ExitCode -ne 0){continue}
 $xml=(Join-Path $dir ('legacy_'+($task -replace '[^A-Za-z0-9_-]','_')+'_'+(Get-Date -Format yyyyMMdd_HHmmss)+'.xml'))
 & schtasks.exe /Query /TN $task /XML | Set-Content -LiteralPath $xml -Encoding UTF8
 if($LASTEXITCODE -ne 0){throw ('HOLD_LEGACY_TASK_BACKUP_FAILED_'+$task)}
 & schtasks.exe /Change /TN $task /Disable
 if($LASTEXITCODE -ne 0){throw ('HOLD_OLD_TASK_NOT_DISABLED_'+$task)}
 Write-Host ('LEGACY_TASK_DISABLED '+$task)
}
$tasks=@(
 @{Name='NOX-V3-Checkpoint-Sync';File='nox_windows_v3_receiver.ps1'},
 @{Name='NOX-V3-Identity-Sync';File='nox_windows_identity_sync.ps1'},
 @{Name='NOX-V3-Cutover-Retry';File='nox_windows_v3_cutover_retry.ps1'}
)
foreach($task in $tasks){
 $script=Join-Path $dir $task.File
 $tr='powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$script+'"'
 & schtasks.exe /Create /F /SC MINUTE /MO 3 /TN $task.Name /TR $tr
 if($LASTEXITCODE -ne 0){throw ('HOLD_SCHEDULE_FAILED_'+$task.Name)}
 & schtasks.exe /Run /TN $task.Name
 Write-Host ('V3_TASK_SCHEDULED '+$task.Name)
}
# Request a non-destructive handoff once on each Pod; incomplete savepoints => HOLD.
$nodes=@(@{Name='A5000';Host='69.30.85.188';Port='22199'},@{Name='A40';Host='69.30.85.193';Port='22088'})
foreach($node in $nodes){
 $remote='python3 /workspace/nox/dispatcher/nox_v3/bin/nox_v3_cutover.py --node '+$node.Name
 & ssh.exe -T -i $key -p $node.Port -o BatchMode=yes -o ConnectTimeout=18 ('root@'+$node.Host) $remote
 if($LASTEXITCODE -ne 0){Write-Warning ('NOX_CUTOVER_HOLD_'+$node.Name)}
}
Write-Host 'NOX_V3_WINDOWS_SYNC_AND_SAVEPOINT_HANDOFF_REQUESTED'
Write-Host ('WINDOWS_ROOT='+$root)
