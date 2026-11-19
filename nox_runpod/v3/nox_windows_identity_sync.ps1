# NOX V3: copy factual GENESIS history from shared A40 to Windows after SHA verification.
$ErrorActionPreference='Stop'
$key=Join-Path $env:USERPROFILE '.ssh\nox_runpod_ed25519'
$target='root@69.30.85.193'
$port='22088'
$dest='C:\NOX_HELION\NOX_NEW\memory\NOX_SELF_MODEL'
if(!(Test-Path $key)){throw 'HOLD_SSH_KEY_MISSING'}
New-Item -ItemType Directory -Force -Path $dest | Out-Null
$mutex=[System.Threading.Mutex]::new($false,'Global\NOX_V3_IDENTITY_SYNC')
$locked=$false
try {
 $locked=$mutex.WaitOne(0)
 if(!$locked){Write-Host 'NOX_IDENTITY_SYNC_ALREADY_RUNNING';return}
 foreach($name in @('state.json','genesis_ledger.jsonl')) {
  $remote="/workspace/nox/memory/NOX_SELF_MODEL/$name"
  $cmd="test -s '$remote' && sha256sum '$remote' || echo HOLD_MISSING"
  $lines=@(& ssh.exe -T -i $key -p $port -o BatchMode=yes -o ConnectTimeout=20 $target $cmd)
  if($LASTEXITCODE -ne 0){Write-Warning "NOX_IDENTITY_SSH_HOLD $name";continue}
  if(!$lines.Count -or $lines[0] -eq 'HOLD_MISSING'){Write-Host "HOLD_IDENTITY_NOT_GENERATED $name";continue}
  $expected=($lines[0] -split '\s+')[0].ToLowerInvariant()
  if($expected -notmatch '^[a-f0-9]{64}$'){throw "HOLD_REMOTE_SHA_INVALID $name"}
  $final=Join-Path $dest $name
  if((Test-Path $final) -and (Get-FileHash $final -Algorithm SHA256).Hash.ToLowerInvariant() -eq $expected){
   Write-Host "NOX_IDENTITY_ALREADY_CURRENT $name";continue
  }
  $temp="$final.noxpart"
  $source=$target + ':' + $remote
  & scp.exe -P $port -i $key -o BatchMode=yes -o ServerAliveInterval=30 $source $temp
  if($LASTEXITCODE -ne 0){throw "HOLD_IDENTITY_TRANSFER_FAILED $name"}
  if((Get-FileHash $temp -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected){throw "HOLD_IDENTITY_SHA_MISMATCH $name"}
  Move-Item -LiteralPath $temp -Destination $final -Force
  Write-Host "NOX_IDENTITY_WINDOWS_SHA256_VERIFIED $name"
 }
} finally {
 if($locked){[void]$mutex.ReleaseMutex()}
 $mutex.Dispose()
}
