param([switch]$Scheduled)
$ErrorActionPreference='Stop'
$Key=Join-Path $env:USERPROFILE '.ssh\nox_runpod_ed25519'
$Base='C:\NOX_HELION\NOX_NEW\RUNPOD_BACKUP'
$Self='C:\NOX_HELION\NOX_NEW\scripts\nox_backup_then_clean_2pods.ps1'
$InventoryUrl='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/4cf52c74502ef336e0b4b200a27e4d4d63f1963d/nox_runpod/stage0/nox_windows_backup_manifest.py'
$CleanupUrl='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/c3b78dd2bbe96e54fbe7be554323b3d5fbf45b78/nox_runpod/stage0/nox_cleanup_after_windows_verified.py'
$Nodes=@(
 [pscustomobject]@{Name='A5000';Host='69.30.85.188';Port=22199},
 [pscustomobject]@{Name='A40';Host='69.30.85.193';Port=22088}
)
if(!(Test-Path -LiteralPath $Key)){throw 'NOX_SSH_KEY_NOT_FOUND'}
New-Item -ItemType Directory -Force -Path $Base,(Split-Path $Self) | Out-Null
$Mutex=New-Object System.Threading.Mutex($false,'Global\NOX_TwoPod_VerifiedBackup')
$Locked=$false
function Log([string]$Message) {
 $entry="[$(Get-Date -Format o)] $Message"
 Write-Host $entry
 Add-Content -LiteralPath (Join-Path $Base 'NOX_BACKUP_HISTORY.log') -Value $entry
}
function Remote([object]$Node,[string]$Command) {
 $old=$ErrorActionPreference
 $ErrorActionPreference='Continue'
 try {
  $lines=@(& ssh.exe -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=12 -i $Key -p $Node.Port "root@$($Node.Host)" $Command 2>&1)
  $code=$LASTEXITCODE
 }finally{$ErrorActionPreference=$old}
 if($code -ne 0){throw "SSH_FAILED $($Node.Name) $code : $($lines -join ' ')"}
 return ($lines -join [Environment]::NewLine).Trim()
}
function CopySCP([object]$Node,[string]$From,[string]$To) {
 $old=$ErrorActionPreference
 $ErrorActionPreference='Continue'
 try {
  $out=@(& scp.exe -q -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 -i $Key -P $Node.Port $From $To 2>&1)
  $code=$LASTEXITCODE
 }finally{$ErrorActionPreference=$old}
 if($code -ne 0){throw "SCP_FAILED $($Node.Name) $code : $($out -join ' ')"}
}
function InstallAgent([object]$Node) {
 $cmd="mkdir -p /workspace/nox/tools /workspace/nox/dispatcher; curl -fsSL --retry 3 '$InventoryUrl' -o /workspace/nox/tools/nox_windows_backup_manifest.py.new && python3 -m py_compile /workspace/nox/tools/nox_windows_backup_manifest.py.new && mv /workspace/nox/tools/nox_windows_backup_manifest.py.new /workspace/nox/tools/nox_windows_backup_manifest.py"
 [void](Remote $Node $cmd)
}
function Backup([object]$Node,[string]$Scope,[string]$Subdir) {
 $agent='/workspace/nox/tools/nox_windows_backup_manifest.py'
 $remoteRoot=if($Scope -eq 'shared'){'/workspace/nox'}else{'/opt'}
 $raw=Remote $Node "python3 $agent inventory --scope $Scope"
 $verified=0;$errors=0;$unsupported=0;$copied=0
 foreach($line in ($raw -split '[\r\n]+')){
  if(!$line.Trim()){continue}
  try{$entry=$line | ConvertFrom-Json}catch{$errors++;continue}
  $rel=[string]$entry.relative
  if($rel -notmatch '^[a-zA-Z0-9_./ -]+$' -or $rel -match '(^|/)\.\.(/|$)' -or $rel -match "['|*?<>:]"){
   $unsupported++;Log "UNSUPPORTED_PATH $($Node.Name) $rel";continue
  }
  $dst=Join-Path (Join-Path $Base $Subdir) ($rel.Replace('/','\'))
  New-Item -ItemType Directory -Force -Path (Split-Path $dst)|Out-Null
  try{
   $meta=(Remote $Node "python3 $agent hash --scope $Scope --file '$rel'") | ConvertFrom-Json
   $expected=[string]$meta.sha256
   $valid=$false
   if((Test-Path -LiteralPath $dst) -and (Get-Item -LiteralPath $dst).Length -eq [long]$meta.size){
    $valid=((Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash.ToLowerInvariant() -eq $expected)
   }
   if(!$valid){
    $part=$dst+'.noxpart'
    $src=("root@"+$Node.Host+":"+$remoteRoot+"/"+$rel)
    CopySCP $Node $src $part
    if((Get-FileHash -LiteralPath $part -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected){throw 'LOCAL_SHA256_MISMATCH'}
    Move-Item -LiteralPath $part -Destination $dst -Force
    $copied++
   }
   $after=(Remote $Node "python3 $agent hash --scope $Scope --file '$rel'")|ConvertFrom-Json
   if($after.sha256 -ne $expected -or [long]$after.size -ne [long]$meta.size){throw 'REMOTE_CHANGED_DURING_COPY'}
   $verified++
   if($copied -gt 0 -and ($copied % 20 -eq 0)){Log "BACKUP_PROGRESS $($Node.Name) copied=$copied verified=$verified"}
  }catch{
   $errors++
   Log "BACKUP_ERROR $($Node.Name) $Scope $rel $($_.Exception.Message)"
  }
 }
 return [pscustomobject]@{Verified=$verified;Copied=$copied;Errors=$errors;Unsupported=$unsupported}
}
function ReceiptAndCleanup([object]$Node,[int]$Count) {
 $receipt=[ordered]@{
  status='VERIFIED_BACKUP_COMPLETE'
  backup_target='WINDOWS_NOX_HELION'
  remote_node=$Node.Name
  verified_at=[DateTimeOffset]::UtcNow.ToString('o')
  verified_file_count=$Count
  sha256_failures=0
  copy_errors=0
 }
 $path=Join-Path $Base ("receipt_"+$Node.Name+".json")
 $utf8=New-Object System.Text.UTF8Encoding($false)
 [System.IO.File]::WriteAllText($path,($receipt | ConvertTo-Json -Depth 5),$utf8)
 $remote='/workspace/nox/dispatcher/windows_verified_'+$Node.Name+'.json'
 CopySCP $Node $path ("root@"+$Node.Host+":"+$remote)
 $cmd="curl -fsSL --retry 3 '$CleanupUrl' -o /workspace/nox/tools/nox_cleanup_after_windows_verified.py.new && python3 -m py_compile /workspace/nox/tools/nox_cleanup_after_windows_verified.py.new && mv /workspace/nox/tools/nox_cleanup_after_windows_verified.py.new /workspace/nox/tools/nox_cleanup_after_windows_verified.py && python3 /workspace/nox/tools/nox_cleanup_after_windows_verified.py --receipt $remote --node $($Node.Name)"
 Log ("CLEANUP_RESULT "+$Node.Name+" "+(Remote $Node $cmd))
}
try{
 $Locked=$Mutex.WaitOne(0)
 if(!$Locked){Log 'ALREADY_RUNNING';return}
 if(!$Scheduled){
  $task='powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$Self+'" -Scheduled'
  $old=$ErrorActionPreference
  $ErrorActionPreference='Continue'
  try {$output=@(& schtasks.exe /Create /F /SC MINUTE /MO 5 /TN 'NOX-RunPod-Verified-Backup-Clean' /TR $task 2>&1);$code=$LASTEXITCODE}
  finally{$ErrorActionPreference=$old}
  if($code -eq 0){Log 'WINDOWS_BACKUP_SCHEDULED_5_MIN'}
  else{Log ("TASK_SCHEDULER_FAILED "+($output -join ' '))}
 }
 # A40 low-priority S03 memory ingestion does not load a GPU model or interfere with active CUDA.
 $memoryUrl='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/5cef7521fe34c459b9a5d9ced6b1def20ee08b81/nox_runpod/stage0/start_a40_unified_nox_memory.sh'
 try{
  Log ("A40_MEMORY "+(Remote $Nodes[1] "curl -fsSL --retry 3 '$memoryUrl' | bash"))
 }catch{Log ("A40_MEMORY_HOLD "+$_.Exception.Message)}
 foreach($node in $Nodes){InstallAgent $node}
 # Both Pods share one /workspace: backup once, via A5000.
 $shared=Backup $Nodes[0] 'shared' 'SHARED_NOX'
 $a5000=Backup $Nodes[0] 'container' 'A5000_CONTAINER'
 $a40=Backup $Nodes[1] 'container' 'A40_CONTAINER'
 $errors=$shared.Errors+$a5000.Errors+$a40.Errors
 $unsupported=$shared.Unsupported+$a5000.Unsupported+$a40.Unsupported
 Log "BACKUP_SUMMARY shared=$($shared.Verified) A5000_container=$($a5000.Verified) A40_container=$($a40.Verified) errors=$errors unsupported=$unsupported"
 if($errors -gt 0 -or $unsupported -gt 0 -or $shared.Verified -lt 1){
  Log 'NO_CLEANUP_BACKUP_NOT_VERIFIED';return
 }
 foreach($node in $Nodes){
  $count=$shared.Verified
  if($node.Name -eq 'A5000'){$count+=$a5000.Verified}else{$count+=$a40.Verified}
  try{ReceiptAndCleanup $node $count}
  catch{Log "CLEANUP_HOLD $($node.Name) $($_.Exception.Message)"}
 }
 Log 'NOX_BACKUP_AND_SAFE_CACHE_CLEANUP_COMPLETE'
}finally{
 if($Locked){$Mutex.ReleaseMutex()}
 $Mutex.Dispose()
}
