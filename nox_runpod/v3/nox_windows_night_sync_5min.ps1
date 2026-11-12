# NOX Windows: safe verified full-weight backup + consistent S03 backup.
# Designed for Task Scheduler every five minutes. Never overwrites a verified checkpoint.
$ErrorActionPreference='Stop'
$Root='C:\NOX_HELION\NOX_NEW\RUNPOD_BACKUP'
$Key=Join-Path $env:USERPROFILE '.ssh\nox_runpod_ed25519'
$HostName='root@69.30.85.193'
$Port='22088'
$Log=Join-Path $Root 'NOX_SYNC_5MIN.log'
New-Item -ItemType Directory -Force -Path $Root | Out-Null
$mtx=[System.Threading.Mutex]::new($false,'Global\NOX_NIGHT_SYNC_EXCLUSIVE')
$hasLock=$false
try{
 $hasLock=$mtx.WaitOne(0)
 if(-not $hasLock){Write-Host 'NOX_SYNC_ALREADY_RUNNING';return}
 if(-not (Test-Path $Key)){throw 'SSH_KEY_MISSING'}
 $first='C:\NOX_HELION\NOX_NEW\RUNPOD_BACKUP\NOX_PRIME_FULL_WEIGHTS'
 $receiver=Join-Path $Root 'NOX_RECEIVER.ps1'
 if(Test-Path $receiver){
  try{& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $receiver | Tee-Object -FilePath $Log -Append}catch{Add-Content $Log "CHECKPOINT_HOLD $($_.Exception.Message)"}
 }
 # A live SQLite database is never copied directly. Remote backup API creates a
 # consistent temporary snapshot; scp + SHA before atomic Windows promotion.
 $source='/workspace/nox/memory/NOX_UNIFIED_S03/unified_nox_knowledge.sqlite3'
 $snap='/tmp/nox_win_s03_snapshot.sqlite3'
 $py=@'
import hashlib,json,os,pathlib,sqlite3
src=pathlib.Path("/workspace/nox/memory/NOX_UNIFIED_S03/unified_nox_knowledge.sqlite3")
dst=pathlib.Path("/tmp/nox_win_s03_snapshot.sqlite3")
if not src.is_file():raise SystemExit("HOLD_S03_MISSING")
if dst.exists():dst.unlink()
a=sqlite3.connect("file:"+str(src)+"?mode=ro",uri=True,timeout=30)
b=sqlite3.connect(str(dst),timeout=30)
with b:a.backup(b)
b.close();a.close()
h=hashlib.sha256()
with dst.open("rb") as f:
 for c in iter(lambda:f.read(8*1024*1024),b""):h.update(c)
print(json.dumps({"bytes":dst.stat().st_size,"sha256":h.hexdigest()}))
'@
 $encoded=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($py))
 $output=@(& ssh.exe -T -i $Key -p $Port -o BatchMode=yes -o ConnectTimeout=20 $HostName "echo '$encoded' | base64 -d | python3")
 if($LASTEXITCODE -ne 0){throw 'S03_REMOTE_BACKUP_FAILED'}
 $proof=($output -join [Environment]::NewLine)|ConvertFrom-Json
 $target=Join-Path $Root 'NOX_S03_VERIFIED.sqlite3'
 $part=$target+'.noxpart'
 & scp.exe -P $Port -i $Key -o BatchMode=yes -o ConnectTimeout=20 ($HostName+':'+$snap) $part
 if($LASTEXITCODE -ne 0){throw 'S03_SCP_FAILED'}
 if((Get-FileHash $part -Algorithm SHA256).Hash -ine [string]$proof.sha256){throw 'S03_HASH_MISMATCH'}
 Move-Item -LiteralPath $part -Destination $target -Force
 Add-Content $Log "$([DateTimeOffset]::UtcNow.ToString('o')) S03_WINDOWS_SHA256_VERIFIED $($proof.sha256)"
 & ssh.exe -T -i $Key -p $Port -o BatchMode=yes $HostName "rm -f '$snap'" | Out-Null
 Write-Host 'S03_WINDOWS_SHA256_VERIFIED'
}catch{
 Add-Content $Log "$([DateTimeOffset]::UtcNow.ToString('o')) HOLD $($_.Exception.Message)"
 Write-Host "NOX_SYNC_HOLD: $($_.Exception.Message)"
}finally{
 if($hasLock){[void]$mtx.ReleaseMutex()}
 $mtx.Dispose()
}
