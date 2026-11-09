$ErrorActionPreference='Stop'
$ip='69.30.85.188'; $port=22199; $pod='erkgy956g04n6c'
$key=Join-Path $env:USERPROFILE '.ssh\nox_runpod_ed25519'
$base='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/'
$tools=Join-Path $env:TEMP 'NOX_Genesis_9B_NEW_GPU'
New-Item -ItemType Directory -Force -Path $tools | Out-Null
if(!(Test-Path -LiteralPath $key -PathType Leaf)){throw 'SSH key not found'}
$ssh=@('-i',$key,'-p',[string]$port,'-o','BatchMode=yes','-o','ConnectTimeout=20','-o','StrictHostKeyChecking=accept-new')
$remote="root@$ip"
function Remote([string]$cmd) {
 & ssh @ssh $remote $cmd
 if($LASTEXITCODE -ne 0){throw "Remote command failed: $cmd"}
}
function Fetch([string]$url,[string]$name) {
 $path=Join-Path $tools $name
 Invoke-WebRequest -Uri $url -OutFile $path -ErrorAction Stop
 if(!(Test-Path -LiteralPath $path)){throw "Fetch failed: $url"}
 return $path
}
Write-Host 'NOX 9B: source transfer -> independent RunPod training -> merged full model' -ForegroundColor Cyan
Remote 'mkdir -p /workspace/nox/models /workspace/nox/embryo /workspace/nox/logs /workspace/nox/tools; test "$(df -P /workspace | tail -1 | awk ''{print $6}'')" = /workspace'
$has9=& ssh @ssh $remote 'test -s /workspace/nox/models/NOX_PRIME_9B_INHERITED/transfer_manifest.json'
if($LASTEXITCODE -ne 0) {
 $src=Fetch ($base+'d22b56c3cf15da5224647d1a85a272db617eefe9/nox_runpod/stage0/windows_transfer.ps1') 'transfer_9b.ps1'
 & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $src -HostName $ip -Port $port -Upload
 if($LASTEXITCODE -ne 0){throw 'Teacher 9B upload failed. Do not train.'}
} else {Write-Host 'Teacher 9B manifest present; skipping 19GB upload.' -ForegroundColor Green}
$hasEmb=& ssh @ssh $remote 'test -s /workspace/nox/embryo/NOX_EMBRYO_TRANSFER_STAGE/embryo_manifest.json'
if($LASTEXITCODE -ne 0) {
 $src=Fetch ($base+'d22b56c3cf15da5224647d1a85a272db617eefe9/nox_runpod/stage0/windows_upload_existing_embryo.ps1') 'transfer_embryo.ps1'
 & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $src -HostName $ip -Port $port
 if($LASTEXITCODE -ne 0){throw 'Original NOX Embryo upload failed. Do not train.'}
} else {Write-Host 'Original NOX Embryo manifest present; skipping upload.' -ForegroundColor Green}
# Check actual source sizes/checksums, not only names.
$verify=@'
import hashlib,json,pathlib
sets=[("/workspace/nox/models/NOX_PRIME_9B_INHERITED","transfer_manifest.json"),("/workspace/nox/embryo/NOX_EMBRYO_TRANSFER_STAGE","embryo_manifest.json")]
for folder,manifest in sets:
 root=pathlib.Path(folder)
 rows=json.loads((root/manifest).read_text(encoding="utf-8-sig"))
 if isinstance(rows,dict):rows=[rows]
 for r in rows:
  p=root/r["path"]
  assert p.is_file() and p.stat().st_size==r["size"], "missing "+str(p)
  h=hashlib.sha256()
  with p.open("rb") as f:
   for b in iter(lambda:f.read(4*1024*1024),b""):h.update(b)
  assert h.hexdigest()==r["sha256"],"checksum "+str(p)
 print("SOURCE_VERIFIED",len(rows),root,flush=True)
'@
$encoded=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($verify))
Remote "echo '$encoded' | base64 -d | python3"
$runUrl=$base+'4f36c147b9360a9321905c99bcfc918743368fe8/nox_runpod/stage0/run_new_a5000_9b_autonomous.sh'
# Do not duplicate active trainer. Detach from Windows with setsid.
$start="mkdir -p /workspace/nox/logs /workspace/nox/tools; if pgrep -af '[r]un_new_a5000_9b_autonomous.sh' | grep -q .; then echo NOX_9B_ALREADY_RUNNING; else curl -fLsS --retry 3 '$runUrl' -o /workspace/nox/tools/run_new_a5000_9b_autonomous.sh && bash -n /workspace/nox/tools/run_new_a5000_9b_autonomous.sh && nohup setsid bash /workspace/nox/tools/run_new_a5000_9b_autonomous.sh </dev/null >> /workspace/nox/logs/NOX_9B_AUTONOMOUS.log 2>&1 & echo NOX_9B_DETACHED_REQUESTED; fi"
Remote $start
Write-Host 'Upload verified. Training requested on RunPod. Windows may be shut down after you see NOX_9B_DETACHED_REQUESTED.' -ForegroundColor Green
Write-Host 'Do not delete original or source disk. Actual steps and merged-model evidence are saved on /workspace.' -ForegroundColor Yellow
