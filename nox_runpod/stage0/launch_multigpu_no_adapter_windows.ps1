$ErrorActionPreference='Stop'
$key=Join-Path $env:USERPROFILE '.ssh\nox_runpod_ed25519'
$dir='C:\NOX_HELION\NOX_NEW\scripts'
$backup=Join-Path $dir 'nox_backup_27b_all.ps1'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
if(!(Test-Path -LiteralPath $key)){throw 'NOX_SSH_KEY_MISSING'}
$url='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/595ea7f886d208e677dec62e586fcbbe961f9557/nox_runpod/stage0/start_multigpu_no_adapter_controller.sh'
function Launch([string]$role,[string]$ip,[int]$port){
 $cmd="curl -fLsS --retry 3 '$url' | bash -s -- '$role'"
 $previous=$ErrorActionPreference
 $ErrorActionPreference='Continue'
 try{
  & ssh.exe -o StrictHostKeyChecking=accept-new -o ConnectTimeout=12 -i $key -p $port ('root@'+$ip) $cmd
  $rc=$LASTEXITCODE
 }finally{$ErrorActionPreference=$previous}
 if($rc -ne 0){Write-Warning ('NOX_'+$role+'_REMOTE_HOLD_'+$rc)}
}
Launch 'A5000' '69.30.85.188' 22199
Launch 'A40' '69.30.85.193' 22088
$burl='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/1e219c842eb7f4a62e69ce977c8d48656e7a6712/nox_runpod/stage0/nox_backup_27b_all.ps1'
Invoke-WebRequest -UseBasicParsing $burl -OutFile $backup
$task='powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$backup+'" -BackupOnly'
$previous=$ErrorActionPreference
$ErrorActionPreference='Continue'
try{
 & schtasks.exe /Create /F /SC MINUTE /MO 5 /TN 'NOX-RunPod-Backup-5min' /TR $task
 $rc=$LASTEXITCODE
}finally{$ErrorActionPreference=$previous}
if($rc -ne 0){Write-Warning 'WINDOWS_BACKUP_TASK_SCHEDULE_FAILED'}
Start-Process powershell.exe -ArgumentList ('-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$backup+'" -BackupOnly') -WindowStyle Hidden
Write-Host 'NOX_MULTI_GPU_CONTROLLER_SUBMITTED A5000=2 A40=4'
Write-Host 'WINDOWS_BACKUP_EVERY_5_MINUTES_REQUESTED'
Write-Host 'MODE=ADAPTERS_PROHIBITED; FULL_WEIGHTS_ONLY_AFTER_REAL_SAFETY_GATE'
