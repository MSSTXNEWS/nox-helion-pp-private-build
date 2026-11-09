param([Parameter(Mandatory)][string]$HostName,[Parameter(Mandatory)][int]$Port)
$ErrorActionPreference='Stop'
$root='C:\NOX_HELION\NOX_NEW\brain\NOX_EMBRYO_GENESIS_V1'
$key=Join-Path $env:USERPROFILE '.ssh\nox_runpod_ed25519'
if(!(Test-Path -LiteralPath $root -PathType Container)){throw "Existing NOX Embryo V1 missing; nothing uploaded"}
if(!(Test-Path -LiteralPath $key -PathType Leaf)){throw 'SSH key missing'}
$files=@(Get-ChildItem -LiteralPath $root -Recurse -File -ErrorAction Stop | Where-Object {
    $_.Extension -in '.safetensors','.pt','.pth','.bin','.json','.model','.tiktoken','.py' -and
    $_.FullName -notmatch '(?i)[\\/](venv|\.venv|site-packages|node_modules|\.git|__pycache__|cache|logs|data|history|memory|S03|chat|private|secrets|credentials)[\\/]' -and
    $_.Name -notmatch '(?i)(secret|credential|api.key|password|identity)'
})
$weights=@($files | Where-Object {$_.Extension -in '.safetensors','.pt','.pth','.bin'})
if($weights.Count -eq 0){throw 'No existing embryo checkpoint weight file; refusing new fake embryo'}
$stage=Join-Path $env:TEMP 'NOX_EMBRYO_TRANSFER_STAGE'
if(Test-Path -LiteralPath $stage){Remove-Item -LiteralPath $stage -Recurse -Force}
New-Item -ItemType Directory -Force -Path $stage | Out-Null
$manifest=@()
foreach($file in $files){
  $rel=$file.FullName.Substring($root.TrimEnd('\').Length+1)
  $dst=Join-Path $stage $rel
  New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null
  Copy-Item -LiteralPath $file.FullName -Destination $dst -ErrorAction Stop
  $manifest+= [ordered]@{path=$rel.Replace('\','/');size=$file.Length;sha256=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
}
ConvertTo-Json -InputObject $manifest -Depth 5 | Set-Content -LiteralPath (Join-Path $stage 'embryo_manifest.json') -Encoding UTF8
Write-Host ("Embryo staged files: {0}, weight/checkpoint files: {1}" -f $files.Count,$weights.Count)
$ssh=@('-i',$key,'-p',"$Port",'-o','BatchMode=yes','-o','ConnectTimeout=15','-o','StrictHostKeyChecking=accept-new')
$dest='root@'+$HostName
& ssh @ssh $dest 'test -f /workspace/nox/models/NOX_PRIME_9B_INHERITED/config.json && mkdir -p /workspace/nox/embryo'
if($LASTEXITCODE -ne 0){throw 'SSH connection or 9B source missing; no upload'}
$target=$dest+':/workspace/nox/embryo/'
& scp -r -i $key -P $Port -o BatchMode=yes -o StrictHostKeyChecking=accept-new $stage $target
if($LASTEXITCODE -ne 0){throw 'SCP upload failed. Original checkpoint remains unchanged'}
$py=@'
import json,pathlib,hashlib
p=pathlib.Path("/workspace/nox/embryo/NOX_EMBRYO_TRANSFER_STAGE")
rows=json.loads((p/"embryo_manifest.json").read_text(encoding="utf-8-sig"))
if isinstance(rows,dict):rows=[rows]
for row in rows:
 f=p/row["path"]
 assert f.is_file() and f.stat().st_size==row["size"],str(f)
 h=hashlib.sha256()
 with f.open("rb") as stream:
  for chunk in iter(lambda:stream.read(4*1024*1024),b""):h.update(chunk)
 assert h.hexdigest()==row["sha256"],str(f)
print("NOX_EMBRYO_ORIGINAL_TRANSFER_VERIFIED",len(rows),flush=True)
'@
$b64=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($py))
& ssh @ssh $dest "echo '$b64' | base64 -d | python"
if($LASTEXITCODE -ne 0){throw 'Remote SHA256 failed; no training authorized'}
Write-Host 'Embryo transfer verified; originals preserved. No training performed by this transfer script.'
