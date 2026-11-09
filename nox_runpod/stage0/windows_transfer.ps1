param(
  [Parameter(Mandatory=$true)][string]$HostName,
  [Parameter(Mandatory=$true)][int]$Port,
  [switch]$Upload,
  [string]$ModelPath='C:\NOX_HELION\NOX_NEW\brain\prime\models\NOX_PRIME_9B_INHERITED',
  [string]$KeyPath="$env:USERPROFILE\.ssh\nox_runpod_ed25519"
)
# NOX PRIME: read-only local model, upload to RunPod with SHA256 verification.
# The cloud Pod must already be running, have direct SSH and persistent /workspace.
$ErrorActionPreference='Stop'
if(!(Test-Path -LiteralPath $KeyPath -PathType Leaf)){throw "SSH private key missing: $KeyPath"}
if(!(Test-Path -LiteralPath $ModelPath -PathType Container)){throw "Original model missing: $ModelPath"}
$files=@(Get-ChildItem -LiteralPath $ModelPath -Recurse -File -ErrorAction Stop)
$weights=@($files | Where-Object {$_.Extension -eq '.safetensors'})
if($weights.Count -ne 4){throw "Expected four local .safetensors shards; found $($weights.Count). STOP"}
if(!(Test-Path -LiteralPath (Join-Path $ModelPath 'config.json'))){throw 'NOX config.json missing'}
$cfg=Get-Content -LiteralPath (Join-Path $ModelPath 'config.json') -Raw | ConvertFrom-Json
if($cfg.model_type -ne 'qwen3_5'){throw "Unexpected model type $($cfg.model_type)"}
if(-not (Get-Command ssh -ErrorAction SilentlyContinue)){throw 'Windows OpenSSH client missing'}
if(-not (Get-Command scp -ErrorAction SilentlyContinue)){throw 'Windows scp client missing'}
Write-Host "NOX model preflight: $($weights.Count) shards; $([math]::Round((($weights | Measure-Object Length -Sum).Sum)/1GB,2)) GiB"
$manifestPath=Join-Path $env:TEMP 'nox_prime_transfer_manifest.json'
$root=(Resolve-Path -LiteralPath $ModelPath).Path.TrimEnd('\')
$manifest=@($files | ForEach-Object {
  $rel=$_.FullName.Substring($root.Length+1).Replace('\','/')
  [ordered]@{path=$rel; size=$_.Length; sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
})
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding UTF8
$sshOpts=@('-o','BatchMode=yes','-o','StrictHostKeyChecking=accept-new','-o','ConnectTimeout=15','-i',$KeyPath,'-p',"$Port")
$dest="root@$HostName"
$prep='mkdir -p /workspace/nox/models && test "$(df -P /workspace | tail -1 | awk ''{print $6}'')" = "/workspace" && nvidia-smi --query-gpu=name,memory.total --format=csv,noheader'
Write-Host 'Checking SSH, GPU, and mounted persistent /workspace ...'
& ssh @sshOpts $dest $prep
if($LASTEXITCODE -ne 0){throw 'Remote preflight failed. Verify direct SSH and the /workspace mount before transferring anything.'}
if(-not $Upload){Write-Host 'PREFLIGHT PASS: to copy the model, rerun with -Upload. GPU is still billable while running.';exit 0}
$remoteModel="/workspace/nox/models/NOX_PRIME_9B_INHERITED"
Write-Host 'Transferring original NOX files; no local deletions or modifications.'
& scp -r -P $Port -i $KeyPath -o 'BatchMode=yes' -o 'StrictHostKeyChecking=accept-new' -o 'ConnectTimeout=15' -- $ModelPath ($dest+':/workspace/nox/models/')
if($LASTEXITCODE -ne 0){throw 'SCP transfer failed; original Windows files unchanged.'}
& scp -P $Port -i $KeyPath -o 'BatchMode=yes' -o 'StrictHostKeyChecking=accept-new' -- $manifestPath ($dest+':/workspace/nox/models/NOX_PRIME_9B_INHERITED/transfer_manifest.json')
if($LASTEXITCODE -ne 0){throw 'Manifest upload failed'}
$verify=@'
import json,hashlib,pathlib,sys
root=pathlib.Path("/workspace/nox/models/NOX_PRIME_9B_INHERITED")
manifest=json.loads((root/"transfer_manifest.json").read_text(encoding="utf-8-sig"))
for item in manifest:
    p=root/item["path"]
    if not p.is_file() or p.stat().st_size != item["size"]:
        print("MISSING_OR_SIZE_MISMATCH",item["path"],flush=True);sys.exit(2)
    digest=hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda:f.read(4*1024*1024),b""): digest.update(chunk)
    if digest.hexdigest()!=item["sha256"]:
        print("HASH_MISMATCH",item["path"],flush=True);sys.exit(3)
print("TRANSFER_VERIFIED",len(manifest),"files",flush=True)
'@
$encoded=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($verify))
& ssh @sshOpts $dest "echo '$encoded' | base64 -d | python"
if($LASTEXITCODE -ne 0){throw 'Remote SHA256 verification FAILED; do not train.'}
Write-Host 'TRANSFER_VERIFIED: NOX PRIME original model copied and verified. This does not train or distill the model.'
