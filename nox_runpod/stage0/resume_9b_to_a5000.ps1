param()
$ErrorActionPreference='Stop'
$key=Join-Path $env:USERPROFILE '.ssh\nox_runpod_ed25519'
if(!(Test-Path $key)){throw 'Missing SSH key'}
$src='194.68.245.68';$sp=22169;$dst='69.30.85.251';$dp=22189
$base=@('-i',$key,'-o','BatchMode=yes','-o','ConnectTimeout=20','-o','StrictHostKeyChecking=accept-new')
function Run([string]$hostip,[int]$port,[string]$cmd) {
 $enc=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($cmd))
 & ssh @base -p $port ('root@'+$hostip) ('echo '+$enc+' | base64 -d | bash')
 if($LASTEXITCODE -ne 0){throw ('SSH failed: '+$hostip)}
}
function Read([string]$hostip,[int]$port,[string]$cmd){
 $enc=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($cmd))
 $result=& ssh @base -p $port ('root@'+$hostip) ('echo '+$enc+' | base64 -d | bash')
 if($LASTEXITCODE -ne 0){throw ('SSH failed: '+$hostip)}
 return $result
}
Run $src $sp 'test -f /workspace/nox/models/NOX_PRIME_9B_INHERITED/transfer_manifest.json && command -v python'
Run $dst $dp 'test -d /workspace && mkdir -p /workspace/nox/models/NOX_PRIME_9B_INHERITED'
Write-Host 'SOURCE 9B:' -ForegroundColor Cyan
Run $src $sp 'du -sh /workspace/nox/models/NOX_PRIME_9B_INHERITED'
Write-Host 'TARGET 9B BEFORE:' -ForegroundColor Cyan
Run $dst $dp 'du -sh /workspace/nox/models/NOX_PRIME_9B_INHERITED'
$pub= (Read $src $sp 'umask 077; test -f /tmp/nox_resume_ed25519 || ssh-keygen -q -t ed25519 -N "" -f /tmp/nox_resume_ed25519; cat /tmp/nox_resume_ed25519.pub' | Select-Object -Last 1).Trim()
if($pub -notmatch '^ssh-ed25519 [A-Za-z0-9+/=]+'){throw 'Invalid temporary transfer public key'}
$pb64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($pub))
Run $dst $dp ("set -e; mkdir -p /root/.ssh; chmod 700 /root/.ssh; touch /root/.ssh/authorized_keys; chmod 600 /root/.ssh/authorized_keys; echo '"+$pb64+"' | base64 -d >> /root/.ssh/authorized_keys; echo >> /root/.ssh/authorized_keys")
try {
 Run $src $sp 'if ! command -v rsync >/dev/null; then apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -qq -y rsync; fi'
 Run $dst $dp 'if ! command -v rsync >/dev/null; then apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -qq -y rsync; fi'
 $cmd=@'
set -euo pipefail
if pgrep -af '[t]ar -C /workspace/nox/models -cf -' | grep -q .; then echo 'OLD_TRANSFER_ACTIVE: stop the old PowerShell transfer first';exit 31;fi
rsync -avh --partial --append-verify --info=progress2 --timeout=120 -e "ssh -i /tmp/nox_resume_ed25519 -p 22189 -o BatchMode=yes -o StrictHostKeyChecking=accept-new" /workspace/nox/models/NOX_PRIME_9B_INHERITED/ root@69.30.85.251:/workspace/nox/models/NOX_PRIME_9B_INHERITED/
'@
 Run $src $sp $cmd
 $verify=@'
set -e
python - <<'PY'
import hashlib,json,pathlib
p=pathlib.Path("/workspace/nox/models/NOX_PRIME_9B_INHERITED")
items=json.loads((p/"transfer_manifest.json").read_text(encoding="utf-8-sig"))
for a in items:
 f=p/a["path"]
 assert f.is_file() and f.stat().st_size==a["size"],"MISSING "+a["path"]
 h=hashlib.sha256()
 with f.open("rb") as s:
  for block in iter(lambda:s.read(4*1024*1024),b""):h.update(block)
 assert h.hexdigest()==a["sha256"],"SHA_MISMATCH "+a["path"]
print("CLOUD_TRANSFER_VERIFIED",len(items),"files")
PY
'@
 Run $dst $dp $verify
} finally {
 $cleanup="python -c 'import pathlib,base64; p=pathlib.Path("+[char]34+"/root/.ssh/authorized_keys"+[char]34+"); k=base64.b64decode("+[char]34+$pb64+[char]34+").decode();p.write_text(chr(10).join(x for x in p.read_text().splitlines() if x.strip()!=k)+chr(10))'"
 try{Run $dst $dp $cleanup}catch{Write-Warning 'Review temporary SSH authorization'}
 try{Run $src $sp 'rm -f /tmp/nox_resume_ed25519 /tmp/nox_resume_ed25519.pub'}catch{Write-Warning 'Review temporary SSH key'}
}
Write-Host 'NOX 9B VERIFIED ON RTX A5000. Local and source models untouched.' -ForegroundColor Green
