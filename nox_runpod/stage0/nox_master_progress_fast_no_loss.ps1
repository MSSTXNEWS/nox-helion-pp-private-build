# NOX HELION one-command coordinator (Windows PowerShell 5.1 compatible).
# Stage 1: A40 knowledge unification
# Stage 2: minimal read-only progress on A5000 and A40
# Stage 3: verified Windows backup every five minutes (no duplicate invocation)
# Stage 4: print exact progress from each Pod
# NEVER downloads/starts another 9B model, trains adapters, or kills active GPU jobs.
$ErrorActionPreference='Stop'
$k=Join-Path $env:USERPROFILE '.ssh\nox_runpod_ed25519'
$repo='MSSTXNEWS/nox-helion-pp-private-build'
$launcher='https://raw.githubusercontent.com/'+$repo+'/6836cd762fa5e7fc1e89293f48a66b1c86981cde/nox_runpod/stage0/start_minimal_progress_controller.sh'
$unify='https://raw.githubusercontent.com/'+$repo+'/7dc29955c4e69bdcd870bc3384c9c53bc8dc9689/nox_runpod/stage0/start_a40_three_teacher_unification.sh'
$backup='https://raw.githubusercontent.com/'+$repo+'/10eb9339577cb149a944fd6a23a2154ab302bcb1/nox_runpod/stage0/nox_backup_then_clean_2pods.ps1'
$backupPath='C:\NOX_HELION\NOX_NEW\scripts\nox_backup_then_clean_2pods.ps1'
$nodes=@(
 [pscustomobject]@{Name='A5000';HostName='69.30.85.188';Port=22199},
 [pscustomobject]@{Name='A40';HostName='69.30.85.193';Port=22088}
)
if(-not (Test-Path -LiteralPath $k)){throw "Missing NOX SSH key: $k"}
function Run-Remote($n,[string]$command) {
 Write-Host ("=== "+$n.Name+" ===") -ForegroundColor Cyan
 $old=$ErrorActionPreference
 $ErrorActionPreference='Continue'
 try{
   $output=@(& ssh.exe -o BatchMode=yes -o ConnectTimeout=15 -o StrictHostKeyChecking=accept-new -i $k -p $n.Port ("root@"+$n.HostName) $command 2>&1)
   $rc=$LASTEXITCODE
 }finally{$ErrorActionPreference=$old}
 $output|ForEach-Object{Write-Host $_}
 if($rc -ne 0){throw ("REMOTE_STAGE_FAILED "+$n.Name+" code="+$rc)}
}
Write-Host 'NOX STAGE 1/4: 3-teacher S03 consolidation (no GPU process reload)' -ForegroundColor Yellow
Run-Remote $nodes[1] ("set -o pipefail; curl -fsSL --retry 3 '"+$unify+"' | bash")
Start-Sleep -Seconds 2
Write-Host 'NOX STAGE 2/4: one lightweight progress controller per server' -ForegroundColor Yellow
foreach($n in $nodes){
  Run-Remote $n ("set -o pipefail; curl -fsSL --retry 3 '"+$launcher+"' | bash -s -- "+$n.Name)
  Start-Sleep -Seconds 2
}
Write-Host 'NOX STAGE 3/4: keep the existing 5-minute incremental Windows backup task' -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path (Split-Path $backupPath)|Out-Null
$temp=$backupPath+'.new'
Invoke-WebRequest -UseBasicParsing -Uri $backup -OutFile $temp
if((Get-Item -LiteralPath $temp).Length -lt 4000){throw 'BACKUP_SCRIPT_TOO_SHORT'}
Move-Item -LiteralPath $temp -Destination $backupPath -Force
$taskName='NOX-RunPod-Verified-Backup-Clean'
$old=$ErrorActionPreference
$ErrorActionPreference='Continue'
try { $result=@(& schtasks.exe /Query /TN $taskName 2>&1);$rc=$LASTEXITCODE }
finally {$ErrorActionPreference=$old}
if($rc -ne 0){
  $arg='powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$backupPath+'" -Scheduled'
  $old=$ErrorActionPreference;$ErrorActionPreference='Continue'
  try{$result=@(& schtasks.exe /Create /SC MINUTE /MO 5 /F /TN $taskName /TR $arg 2>&1);$rc=$LASTEXITCODE}
  finally{$ErrorActionPreference=$old}
  if($rc -ne 0){Write-Warning 'Unable to register 5-min backup; no cleanup will be attempted.'}
  else{Write-Host 'NOX_WINDOWS_BACKUP_TASK_REGISTERED_5MIN' -ForegroundColor Green}
}else{Write-Host 'NOX_WINDOWS_BACKUP_5MIN_ALREADY_SCHEDULED' -ForegroundColor Green}
Start-Sleep -Seconds 2
Write-Host 'NOX STAGE 4/4: current truthful progress' -ForegroundColor Yellow
foreach($n in $nodes){
 $cmd="python3 /workspace/nox/tools/nox_absorption_progress_control_$($n.Name).py --node $($n.Name) --once; cat /workspace/nox/dispatcher/absorption_control/$($n.Name)_status.json"
 Run-Remote $n $cmd
}
Write-Host 'NOX_MASTER_COMPLETE: progress monitors alive; NO GPU restart, NO adapters, NO duplicate backups.' -ForegroundColor Green
