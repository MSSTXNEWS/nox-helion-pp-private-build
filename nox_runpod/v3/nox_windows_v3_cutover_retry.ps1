# NOX V3 retry savepoint handoff once every 3 minutes. NO FORCE KILL.
$ErrorActionPreference='Continue'
$key=Join-Path $env:USERPROFILE '.ssh\nox_runpod_ed25519'
if(!(Test-Path $key)){Write-Warning 'HOLD_KEY_MISSING';return}
foreach($node in @(@{Name='A5000';Host='69.30.85.188';Port='22199'},@{Name='A40';Host='69.30.85.193';Port='22088'})){
 $remote='test -s /workspace/nox/dispatcher/nox_v3/bin/nox_v3_cutover.py && python3 /workspace/nox/dispatcher/nox_v3/bin/nox_v3_cutover.py --node '+$node.Name
 & ssh.exe -T -i $key -p $node.Port -o BatchMode=yes -o ConnectTimeout=10 ('root@'+$node.Host) $remote
 if($LASTEXITCODE -ne 0){Write-Host ('NOX_V3_CUTOVER_HOLD '+$node.Name)}
}
