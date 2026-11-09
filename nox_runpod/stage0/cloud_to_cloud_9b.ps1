$ErrorActionPreference='Stop'
$src='194.68.245.68'; $srcPort=22169
$dst='69.30.85.251'; $dstPort=22189
$key=Join-Path $env:USERPROFILE '.ssh\nox_runpod_ed25519'
if(!(Test-Path -LiteralPath $key)){throw 'Missing Windows SSH key'}
$o=@('-i',$key,'-o','BatchMode=yes','-o','ConnectTimeout=20','-o','StrictHostKeyChecking=accept-new')
function Call-Remote($hostIp,$sshPort,$bash){
  $bytes=[Text.Encoding]::UTF8.GetBytes($bash)
  $b64=[Convert]::ToBase64String($bytes)
  & ssh @o -p $sshPort ('root@'+$hostIp) ('echo '+$b64+' | base64 -d | bash')
  if($LASTEXITCODE -ne 0){throw ('Remote command failed at '+$hostIp)}
}
function Read-Remote($hostIp,$sshPort,$bash){
  $b64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($bash))
  $result=& ssh @o -p $sshPort ('root@'+$hostIp) ('echo '+$b64+' | base64 -d | bash')
  if($LASTEXITCODE -ne 0){throw ('Remote read failed at '+$hostIp)}
  return $result
}
Call-Remote $src $srcPort @'
set -e
test -s /workspace/nox/models/NOX_PRIME_9B_INHERITED/transfer_manifest.json
test -f /workspace/nox/models/NOX_PRIME_9B_INHERITED/config.json
'@
Call-Remote $dst $dstPort @'
set -e
test "$(df -P /workspace | tail -1 | awk '{print $6}')" = "/workspace"
mkdir -p /workspace/nox/models
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
'@
$pubScript=@'
set -e
umask 077
if [ ! -f /tmp/nox_a5000_transfer_key ]; then ssh-keygen -q -t ed25519 -N "" -f /tmp/nox_a5000_transfer_key; fi
cat /tmp/nox_a5000_transfer_key.pub
'@
$pub=((Read-Remote $src $srcPort $pubScript)|Select-Object -Last 1).Trim()
if($pub -notmatch '^ssh-ed25519 [A-Za-z0-9+/=]+'){throw 'Invalid transport key'}
$pub64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($pub+[Environment]::NewLine))
$grant="set -e; umask 077; mkdir -p /root/.ssh; touch /root/.ssh/authorized_keys; chmod 600 /root/.ssh/authorized_keys; echo '$pub64' | base64 -d >> /root/.ssh/authorized_keys"
Call-Remote $dst $dstPort $grant
try{
$transfer=@'
set -euo pipefail
tar -C /workspace/nox/models -cf - NOX_PRIME_9B_INHERITED | ssh -i /tmp/nox_a5000_transfer_key -p 22189 -o BatchMode=yes -o ConnectTimeout=20 -o StrictHostKeyChecking=accept-new root@69.30.85.251 'tar -C /workspace/nox/models -xf -'
'@
Write-Host 'RunPod CPU -> GPU A5000 direct cloud transfer ...'
Call-Remote $src $srcPort $transfer
$verify=@'
set -euo pipefail
python - <<'PY'
import json,hashlib,pathlib
p=pathlib.Path("/workspace/nox/models/NOX_PRIME_9B_INHERITED")
items=json.loads((p/"transfer_manifest.json").read_text(encoding="utf-8-sig"))
for item in items:
 f=p/item["path"]
 if not f.is_file() or f.stat().st_size!=item["size"]:raise RuntimeError("SIZE ERROR "+item["path"])
 h=hashlib.sha256()
 with f.open("rb") as s:
  for chunk in iter(lambda:s.read(4194304),b""):h.update(chunk)
 if h.hexdigest()!=item["sha256"]:raise RuntimeError("HASH ERROR "+item["path"])
print("CLOUD_TRANSFER_VERIFIED",len(items),"files")
PY
'@
Call-Remote $dst $dstPort $verify
} finally {
  $b64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($pub))
  $cleanup="python -c 'import base64,pathlib; p=pathlib.Path(""/root/.ssh/authorized_keys""); k=base64.b64decode(""$b64"").decode(); p.write_text(chr(10).join(x for x in p.read_text().splitlines() if x.strip()!=k.strip())+chr(10))'"
  try{Call-Remote $dst $dstPort $cleanup}catch{Write-Warning 'Review temporary destination SSH key cleanup'}
  try{Call-Remote $src $srcPort 'rm -f /tmp/nox_a5000_transfer_key /tmp/nox_a5000_transfer_key.pub'}catch{Write-Warning 'Review source key cleanup'}
}
Write-Host 'NOX 9B now verified on A5000. Source and Windows originals preserved.'
