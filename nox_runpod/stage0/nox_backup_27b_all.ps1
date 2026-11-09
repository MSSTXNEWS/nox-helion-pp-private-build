param([switch]$BackupOnly)
$ErrorActionPreference='Stop'
$Server='69.30.85.188'; $Port=22199
$Key=Join-Path $env:USERPROFILE '.ssh\nox_runpod_ed25519'
$Backup='C:\NOX_HELION\NOX_NEW\RUNPOD_BACKUP'
$Self='C:\NOX_HELION\NOX_NEW\scripts\nox_backup_27b_all.ps1'
$Agent='/workspace/nox/tools/nox_backup_agent.py'
$AgentUrl='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/01038cc2f3e2407754a012baa1cb9d647f804579/nox_runpod/stage0/nox_backup_agent.py'
$DonorUrl='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/36b7bb5bdf4bbb52912e24c031b2db2f07087668/nox_runpod/stage0/teacher_27b_container_verified_v2.sh'
New-Item -ItemType Directory -Force -Path $Backup,(Split-Path $Self) | Out-Null
if(!(Test-Path $Key)){throw 'SSH key missing'}
$Lock=New-Object System.Threading.Mutex($false,'Global\NOX_Backup27B')
$Acquired=$false
function Note([string]$msg){
 $line="[$(Get-Date -Format o)] $msg";Write-Host $line
 Add-Content -LiteralPath (Join-Path $Backup 'NOX_BACKUP_HISTORY.log') -Value $line
}
function Remote([string]$cmd){
 $prev=$ErrorActionPreference;$ErrorActionPreference='Continue'
 try {
  $out=@(& ssh.exe -o BatchMode=yes -o ConnectTimeout=12 -i $Key -p $Port ('root@'+$Server) $cmd 2>&1)
  $code=$LASTEXITCODE
 } finally {$ErrorActionPreference=$prev}
 if($code -ne 0){throw ('SSH exit='+$code+': '+($out -join ' '))}
 return ($out -join [Environment]::NewLine).Trim()
}
try {
 $Acquired=$Lock.WaitOne(0)
 if(!$Acquired){Write-Host 'NOX_BACKUP_ALREADY_RUNNING';return}
 Note 'NOX_BACKUP_STARTED'
 if(!$BackupOnly){
  $launch="mkdir -p /workspace/nox/logs /opt; curl -fLsS '$DonorUrl' -o /opt/nox_teacher_27b_start.sh && bash -n /opt/nox_teacher_27b_start.sh && (pgrep -f '[b]ash /opt/nox_teacher_27b_start.sh' >/dev/null || nohup setsid -f bash /opt/nox_teacher_27b_start.sh </dev/null >>/workspace/nox/logs/NOX_27B_CONTAINER.log 2>&1) && echo NOX_27B_DOWNLOAD_REQUESTED"
  try {Note (Remote $launch)} catch {Note ('DONOR_QUEUE_ERROR '+$_.Exception.Message)}
  $task='powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$Self+'" -BackupOnly'
  $prev=$ErrorActionPreference;$ErrorActionPreference='Continue'
  try {$msg=@(& schtasks.exe /Create /F /SC MINUTE /MO 5 /TN 'NOX-RunPod-Backup-5min' /TR $task 2>&1);$rc=$LASTEXITCODE}
  finally {$ErrorActionPreference=$prev}
  if($rc -eq 0){Note 'NOX_AUTO_BACKUP_REGISTERED_EVERY_5_MIN'}
  else {Note ('SCHEDULE_WARNING '+($msg -join ' '))}
 }
 $setup="mkdir -p /workspace/nox/tools; curl -fsSL '$AgentUrl' -o $Agent.new && python3 -m py_compile $Agent.new && mv -f $Agent.new $Agent"
 [void](Remote $setup)
 $inventory=(Remote ("python3 "+$Agent+" inventory")) | ConvertFrom-Json
 $scanned=0;$verified=0;$failed=0;$newBytes=[long]0
 foreach($item in $inventory.entries){
  $rel=[string]$item.path
  if($rel -notmatch '^[a-zA-Z0-9._/-]+$' -or $rel -match '(^|/)\.\.(/|$)'){continue}
  if($rel.StartsWith('models/NOX_PRIME_9B_INHERITED/')){continue}
  $scanned++
  $local=Join-Path $Backup ($rel.Replace('/','\'))
  New-Item -ItemType Directory -Force -Path (Split-Path $local)|Out-Null
  try{
   $meta=(Remote ("python3 "+$Agent+" hash --path '"+$rel+"'")) | ConvertFrom-Json
   $sha=[string]$meta.sha256
   $valid=$false
   if(Test-Path -LiteralPath $local){
    if((Get-Item -LiteralPath $local).Length -eq [long]$meta.bytes){
     $valid=((Get-FileHash -LiteralPath $local -Algorithm SHA256).Hash.ToLowerInvariant() -eq $sha)
    }
   }
   if(!$valid){
    $part=$local+'.noxpart'
    $source=('root@'+$Server+':/workspace/nox/'+$rel)
    $prev=$ErrorActionPreference;$ErrorActionPreference='Continue'
    try{& scp.exe -q -o BatchMode=yes -o ConnectTimeout=12 -i $Key -P $Port $source $part 2>&1 | Out-Null;$rc=$LASTEXITCODE}
    finally{$ErrorActionPreference=$prev}
    if($rc -ne 0){throw 'SCP_FAILED'}
    if((Get-FileHash -LiteralPath $part -Algorithm SHA256).Hash.ToLowerInvariant() -ne $sha){throw 'SHA_MISMATCH'}
    Move-Item -LiteralPath $part -Destination $local -Force
    $newBytes += [long]$meta.bytes
   }
   $confirmed=(Remote ("python3 "+$Agent+" hash --path '"+$rel+"'")) | ConvertFrom-Json
   if($confirmed.sha256 -ne $sha -or [long]$confirmed.bytes -ne [long]$meta.bytes){throw 'REMOTE_FILE_CHANGED'}
   $verified++;Note ("VERIFIED "+$rel)
   if($rel -match '^logs/[a-zA-Z0-9_.-]+\.(log\.\d+|log\.gz|old\.log|bak)$'){
    try{[void](Remote ("python3 "+$Agent+" prune --path '"+$rel+"' --sha256 '"+$sha+"'"))}
    catch{Note ('OLD_LOG_PRUNE_SKIPPED '+$rel)}
   }
  } catch {$failed++;Note ('COPY_ERROR '+$rel+' '+$_.Exception.Message)}
 }
 Note ("BACKUP_COMPLETE scanned=$scanned verified=$verified failed=$failed new_bytes=$newBytes")
 Note ('SAFE_CACHE '+(Remote ("python3 "+$Agent+" cleanup-cache")))
 Note ('DISKS '+(Remote 'df -h / /workspace | tail -n 2'))
 Note 'NOX_CHECKPOINTS_AND_MODELS_PRESERVED'
} finally {
 if($Acquired){$Lock.ReleaseMutex()}
 $Lock.Dispose()
}
