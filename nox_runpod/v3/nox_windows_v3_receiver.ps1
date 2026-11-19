# NOX Windows receiver: checkpoint only, SHA-256 verified, no remote deletion.
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
 $py=@'
import json,pathlib,hashlib,datetime
base=pathlib.Path("/opt/nox_full_parameter_A40")
choices=[]
for rp in base.glob("NOX_FULL_CYCLE_*/NOX_FULL_TRAIN_RECEIPT.json"):
 try:
  obj=json.loads(rp.read_text())
  if not obj.get("shards") or float(obj.get("after_holdout_loss",1e12))>float(obj.get("baseline_holdout_loss",0))*1.05:continue
  if any(not (rp.parent/s["file"]).is_file() for s in obj["shards"]):continue
  choices.append((rp.stat().st_mtime_ns,rp,obj))
 except (OSError,ValueError,KeyError,TypeError):pass
if not choices:
 print(json.dumps({"status":"HOLD","reason":"NO_ACCEPTED_CHECKPOINT"}));raise SystemExit
_,rp,obj=max(choices,key=lambda x:x[0])
shard_names={s["file"] for s in obj["shards"]}
extras=[]
for p in rp.parent.iterdir():
 if not p.is_file() or p.name in shard_names or p.name=="NOX_FULL_TRAIN_RECEIPT.json":continue
 if len(p.name)>128 or not p.name.endswith((".json",".txt",".model",".tiktoken")):continue
 if p.stat().st_size>200*1024*1024:continue
 h=hashlib.sha256()
 with p.open("rb") as ff:
  for v in iter(lambda:ff.read(4*1024*1024),b""):h.update(v)
 extras.append({"file":p.name,"sha256":h.hexdigest(),"bytes":p.stat().st_size})
print(json.dumps({"status":"READY","path":str(rp.parent),"cycle":obj.get("cycle"),
 "steps":obj.get("steps"),"shards":obj["shards"],"extras":extras}))

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
 if(Test-Path $marker){
  $prior=Get-Content $marker -Raw|ConvertFrom-Json
  if($prior.status -eq 'SHA256_VERIFIED' -and $prior.cycle -eq $status.cycle -and $prior.steps -eq $status.steps){
   Write-Host "NOX_ALREADY_VERIFIED $local";return
  }
 }
 $items=@($status.shards)+@($status.extras)+@([pscustomobject]@{file='NOX_FULL_TRAIN_RECEIPT.json';sha256=$null})
 foreach($item in $items){
  $file=[string]$item.file
  if($file -notmatch '^[A-Za-z0-9_.-]+$' -or $file.Contains('..')){throw "UNSAFE_NAME $file"}
  $dest=Join-Path $local $file
  $expected=[string]$item.sha256
  if($expected -and (Test-Path $dest) -and (Get-FileHash $dest -Algorithm SHA256).Hash -ieq $expected){
   Write-Host "SKIP_VERIFIED $file";continue
  }
  $temp="$dest.noxpart"
  $remote="$($status.path)/$file"
  $scpSource='root@69.30.85.193:'+$remote
  $scpArgs=@('-C','-P','22088','-i',$key,'-o','BatchMode=yes','-o','ServerAliveInterval=30',$scpSource,$temp)
  Write-Host "COPY $file"
  & scp.exe @scpArgs
  if($LASTEXITCODE -ne 0){throw "SCP_FAILED $file"}
  if($expected -and (Get-FileHash $temp -Algorithm SHA256).Hash -ine $expected){throw "SHA_FAILED $file"}
  Move-Item -LiteralPath $temp -Destination $dest -Force
 }
 $receipt=Get-Content (Join-Path $local 'NOX_FULL_TRAIN_RECEIPT.json') -Raw|ConvertFrom-Json
 if($receipt.cycle -ne $status.cycle -or $receipt.steps -ne $status.steps){throw 'RECEIPT_MISMATCH'}
 foreach($s in $receipt.shards){
  $p=Join-Path $local $s.file
  if(!(Test-Path $p) -or (Get-FileHash $p -Algorithm SHA256).Hash -ine $s.sha256){throw "FINAL_SHA_FAILED $($s.file)"}
 }
 $proof=[ordered]@{status='SHA256_VERIFIED';cycle=$receipt.cycle;steps=$receipt.steps;parameter_count=$receipt.parameter_count;teacher_counts=$receipt.teacher_counts;verified_utc=[DateTimeOffset]::UtcNow.ToString('o')}
 $proof|ConvertTo-Json -Depth 8|Set-Content "$marker.tmp" -Encoding UTF8
 Move-Item "$marker.tmp" $marker -Force
 Write-Host "NOX_WINDOWS_CHECKPOINT_VERIFIED $local"
} finally {
 if($locked){[void]$mutex.ReleaseMutex()}
 $mutex.Dispose()
}
