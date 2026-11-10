# NOX one-time Windows installation of 3-minute GitHub control and checkpoint receiver.
$ErrorActionPreference='Stop'
$root='C:\NOX_HELION\NOX_NEW'
$dir=Join-Path $root 'scripts'
$key=Join-Path $env:USERPROFILE '.ssh\nox_runpod_ed25519'
$base='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox_runpod/control'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
if(!(Test-Path $key)){throw "HOLD_SSH_KEY_MISSING $key"}
$remote='curl -fsSL --retry 3 '+$base+'/install_nox_master_poller.sh -o /tmp/nox_control_install.sh && bash /tmp/nox_control_install.sh '
$nodes=@(@{name='A40';host='69.30.85.193';port=22088},@{name='A5000';host='69.30.85.188';port=22199})
foreach($n in $nodes){
 Write-Host "=== INSTALL CONTROL $($n.name) ===" -ForegroundColor Cyan
 $args=@('-T','-i',$key,'-p',"$($n.port)",'-o','BatchMode=yes','-o','ConnectTimeout=20',"root@$($n.host)",($remote+$n.name))
 & ssh.exe @args
 if($LASTEXITCODE -ne 0){throw "HOLD_REMOTE_INSTALL $($n.name)"}
}
$receiver=Join-Path $dir 'nox_windows_verified_receiver.ps1'
$url=$base+'/nox_windows_verified_receiver.ps1'
Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile "$receiver.new"
if((Get-Item "$receiver.new").Length -lt 2500){throw 'HOLD_RECEIVER_SCRIPT_INCOMPLETE'}
Move-Item -Force "$receiver.new" $receiver

# Preserve only the specifically identified superseded scheduled job for manual rollback.
$legacy='NOX-RunPod-Verified-Backup-Clean'
$oldXml=Join-Path $dir ('legacy_task_backup_'+(Get-Date -Format yyyyMMdd_HHmmss)+'.xml')
& schtasks.exe /Query /TN $legacy /XML 2>$null | Set-Content $oldXml -Encoding UTF8
if($LASTEXITCODE -eq 0){
 & schtasks.exe /Change /TN $legacy /Disable
 if($LASTEXITCODE -ne 0){Write-Warning 'LEGACY_WINDOWS_TASK_NOT_DISABLED'}
 else {Write-Host "LEGACY_TASK_DISABLED_BACKUP=$oldXml"}
} else {
 Remove-Item $oldXml -ErrorAction SilentlyContinue
}

$task='NOX-Verified-Windows-Checkpoint-Sync'
$tr='powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$receiver+'"'
& schtasks.exe /Create /F /SC MINUTE /MO 3 /TN $task /TR $tr
if($LASTEXITCODE -ne 0){throw 'HOLD_WINDOWS_SCHEDULE_CREATE_FAILED'}
Write-Host 'NOX_CONTROL_INSTALLED: PODS_POLL_GITHUB_EVERY_180_SECONDS'
Write-Host 'WINDOWS_CHECKPOINT_TRANSFER_SCHEDULED_EVERY_3_MINUTES'
& schtasks.exe /Run /TN $task
if($LASTEXITCODE -ne 0){Write-Warning 'START_TASK_MANUALLY_IF_NEEDED'}
Write-Host "RECEIVER=$receiver"
