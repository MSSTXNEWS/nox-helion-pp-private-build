# NOX legacy A40 Windows checkpoint receiver: read-only remote query and local copy.
# NOT an implementation of the Windows owner /api/install/backup route.
# No implicit remote script installation or overwriting existing owner evidence.
$ErrorActionPreference='Stop'
$root='C:\NOX_HELION\NOX_NEW\RUNPOD_BACKUP\NOX_PRIME_FULL_WEIGHTS'
$key=Join-Path $env:USERPROFILE '.ssh\nox_runpod_ed25519'
New-Item -ItemType Directory -Force -Path $root | Out-Null
if(!(Test-Path $key)){throw 'SSH_KEY_MISSING'}
$mutex=[System.Threading.Mutex]::new($false,'Global\NOX_VERIFIED_A40_TRANSFER')
$locked=$false
try {
 $locked=$mutex.WaitOne(0)
 if(!$locked){Write-Host 'TRANSFER_ALREADY_RUNNING';return}
 $oldScp=@(Get-CimInstance Win32_Process -Filter "Name='scp.exe'" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*nox_full_parameter_A40*' })
 if($oldScp.Count){Write-Host "HOLD_LEGACY_TRANSFER_IN_PROGRESS PID=$($oldScp[0].ProcessId)";return}
 # Only read old A40 progress; do not install/restart controllers on GPU hosts.
 $py=@'
import json,pathlib
f=pathlib.Path("/workspace/nox/dispatcher/a40_full_parameter/progress.json")
if not f.exists(): print(json.dumps({"status":"HOLD","reason":"NO_PROGRESS"}));raise SystemExit
d=json.loads(f.read_text())
out=(d.get("extra") or {}).get("output")
if d.get("status")!="COMPLETE_VERIFIED" or not out:
 print(json.dumps({"status":"HOLD","reason":"NO_VERIFIED_CYCLE"}));raise SystemExit
p=pathlib.Path(out)
if p.parent!=pathlib.Path("/opt/nox_full_parameter_A40") or not p.name.startswith("NOX_FULL_CYCLE_"):
 print(json.dumps({"status":"HOLD","reason":"INVALID_PATH"}));raise SystemExit
r=p/"NOX_FULL_TRAIN_RECEIPT.json"
if not r.is_file(): print(json.dumps({"status":"HOLD","reason":"NO_RECEIPT"}));raise SystemExit
obj=json.loads(r.read_text())
print(json.dumps({"status":"READY","path":str(p),"cycle":obj.get("cycle"),"steps":obj.get("steps"),"shards":obj.get("shards",[])}))
'@
 $b64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($py))
 $sshArgs=@('-T','-i',$key,'-p','22088','-o','BatchMode=yes','-o','ConnectTimeout=20','-o','ServerAliveInterval=30','root@69.30.85.193',"echo '$b64' | base64 -d | python3")
 $lines=@(& ssh.exe @sshArgs)
 if($LASTEXITCODE -ne 0){throw 'SSH_STATUS_FAILED'}
 $status=($lines -join [Environment]::NewLine)|ConvertFrom-Json
 if($status.status -ne 'READY'){Write-Host "NOX_TRANSFER_$($status.status): $($status.reason)";return}
 if($status.path -notmatch '^/opt/nox_full_parameter_A40/NOX_FULL_CYCLE_[A-Za-z0-9_]+_STEP_[0-9]+$'){throw 'INVALID_CHECKPOINT_PATH'}
 $name=($status.path -split '/')[-1]
 $local=Join-Path $root $name
 New-Item -ItemType Directory -Force -Path $local | Out-Null
 $marker=Join-Path $local 'NOX_WINDOWS_VERIFIED.json'
 if(Test-Path -LiteralPath $marker){
  $prior=Get-Content -LiteralPath $marker -Raw | ConvertFrom-Json
  if($prior.status -eq 'SHA256_VERIFIED' -and $prior.cycle -eq $status.cycle -and $prior.steps -eq $status.steps){
   # A stored PASS marker is not proof if a shard disappeared since the last copy.
   $existingReceipt=Join-Path $local 'NOX_FULL_TRAIN_RECEIPT.json'
   if(!(Test-Path -LiteralPath $existingReceipt -PathType Leaf)){throw 'HOLD_VERIFIED_RECEIPT_MISSING'}
   $priorReceipt=Get-Content -LiteralPath $existingReceipt -Raw | ConvertFrom-Json
   if($priorReceipt.cycle -ne $status.cycle -or $priorReceipt.steps -ne $status.steps){throw 'HOLD_VERIFIED_RECEIPT_STALE'}
   foreach($shard in $priorReceipt.shards){
    $filename=[string]$shard.file
    if($filename.Length -eq 0 -or $filename.Contains('..') -or $filename.Contains('/') -or $filename.Contains('\')){
     throw 'HOLD_VERIFIED_SHARD_UNSAFE_NAME'
    }
    $existingShard=Join-Path $local $filename
    if(!(Test-Path -LiteralPath $existingShard -PathType Leaf) -or
       (Get-Item -LiteralPath $existingShard -Force).LinkType -or
       (Get-FileHash -LiteralPath $existingShard -Algorithm SHA256).Hash -ine [string]$shard.sha256){
     throw "HOLD_VERIFIED_SHARD_MISSING_OR_TAMPERED $filename"
    }
   }
   Write-Host "NOX_ALREADY_VERIFIED $local";return
  }
  throw 'HOLD_EXISTING_MARKER_CONFLICT'
 }
 $items=@($status.shards)+@([pscustomobject]@{file='NOX_FULL_TRAIN_RECEIPT.json';sha256=$null})
 foreach($item in $items){
  $file=[string]$item.file
  if($file -notmatch '^[A-Za-z0-9_.-]+$' -or $file.Contains('..')){throw "UNSAFE_NAME $file"}
  $dest=Join-Path $local $file
  $expected=[string]$item.sha256
  if(Test-Path -LiteralPath $dest){
   if($expected -and -not (Get-Item -LiteralPath $dest -Force).LinkType -and
      (Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash -ieq $expected){
    Write-Host "SKIP_VERIFIED $file";continue
   }
   throw "HOLD_EXISTING_BACKUP_CONFLICT $file"
  }
  $temp="$dest.noxpart"
  if(Test-Path -LiteralPath $temp){throw "HOLD_PARTIAL_BACKUP_CONFLICT $file"}
  $remote="$($status.path)/$file"
  $scpArgs=@('-C','-P','22088','-i',$key,'-o','BatchMode=yes','-o','ServerAliveInterval=30',"root@69.30.85.193:$remote",$temp)
  Write-Host "COPY $file"
  & scp.exe @scpArgs
  if($LASTEXITCODE -ne 0){throw "SCP_FAILED $file"}
  if($expected -and (Get-FileHash $temp -Algorithm SHA256).Hash -ine $expected){throw "SHA_FAILED $file"}
  # Atomic no-replace: race with another owner's destination => fail, never overwrite.
  [System.IO.File]::Move($temp,$dest)
 }
 $receipt=Get-Content (Join-Path $local 'NOX_FULL_TRAIN_RECEIPT.json') -Raw|ConvertFrom-Json
 if($receipt.cycle -ne $status.cycle -or $receipt.steps -ne $status.steps){throw 'RECEIPT_MISMATCH'}
 foreach($s in $receipt.shards){
  $p=Join-Path $local $s.file
  if(!(Test-Path $p) -or (Get-FileHash $p -Algorithm SHA256).Hash -ine $s.sha256){throw "FINAL_SHA_FAILED $($s.file)"}
 }
 $proof=[ordered]@{status='SHA256_VERIFIED';cycle=$receipt.cycle;steps=$receipt.steps;parameter_count=$receipt.parameter_count;teacher_counts=$receipt.teacher_counts;verified_utc=[DateTimeOffset]::UtcNow.ToString('o')}
 $proofTemp="$marker.tmp"
 if(Test-Path -LiteralPath $proofTemp){throw 'HOLD_PROOF_TEMP_CONFLICT'}
 $raw=($proof|ConvertTo-Json -Depth 8)+[Environment]::NewLine
 $bytes=[Text.Encoding]::UTF8.GetBytes($raw)
 $stream=[System.IO.FileStream]::new($proofTemp,[System.IO.FileMode]::CreateNew,
          [System.IO.FileAccess]::Write,[System.IO.FileShare]::None)
 try{$stream.Write($bytes,0,$bytes.Length);$stream.Flush($true)}
 finally{$stream.Dispose()}
 [System.IO.File]::Move($proofTemp,$marker)
 Write-Host "NOX_WINDOWS_CHECKPOINT_VERIFIED $local"
} finally {
 if($locked){[void]$mutex.ReleaseMutex()}
 $mutex.Dispose()
}
