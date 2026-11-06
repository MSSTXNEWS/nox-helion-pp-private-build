# NOX HELION ONE BRAIN · first real deployment lane · instructions_version 0.0.6
# Installs no second UI. NEVER touches Downloads. Original EXE remains unchanged.
$ErrorActionPreference="Stop"
$root="C:\NOX_HELION\NOX_NEW"
$brain=Join-Path $root "brain"
$source=Join-Path $brain "source\repo\coordination\soul_gpu_v1"
$logs=Join-Path $brain "logs"
foreach($p in @($root,$brain,$logs,(Join-Path $brain "memory"),(Join-Path $brain "skills"))) {
  New-Item -ItemType Directory -Force -Path $p | Out-Null
}
$log=Join-Path $logs ("ONE_BRAIN_"+(Get-Date -Format "yyyyMMdd-HHmmss")+".log")
function Say([string]$msg) {
 $line="$(Get-Date -Format s) $msg"
 Write-Host $line; Add-Content -LiteralPath $log -Value $line
}
Say "NOX ONE BRAIN START. NO Downloads operations. 70+70+70GB quotas, 60GB free reserve."
if(-not (Test-Path (Join-Path $source "soul_gpu.py"))) {
  throw "Canonical source missing: $source. Run the one-line Git bootstrap first."
}
$native=Join-Path $root "release\NOX.HELION.exe"
if(Test-Path -LiteralPath $native) {
  if(-not (Get-Process -Name "NOX.HELION" -ErrorAction SilentlyContinue)) {
    Start-Process -FilePath $native -WorkingDirectory (Split-Path $native)
    Say "Opened actual NOX.HELION.exe (native binding to new SOUL not verified)"
  } else { Say "Existing native NOX already running" }
} else { Say "Native NOX EXE missing; no second EXE or demo started" }

# Installed Ollama weights remain content-addressed inside NOX. Never re-pull existing tags.
$runner=Join-Path $source "RUN_NOX_BRAIN_MAX_V4.ps1"
if(-not(Test-Path $runner)){throw "Canonical runner missing"}
try {
 & $runner
 $runnerOK=$?
} catch {
 Say ("Runner HOLD: "+$_.Exception.Message)
 $runnerOK=$false
}
Say "Runner ended: $runnerOK. Inspect RUN_RECEIPT.json; downloads never treated as proof of training."

# This existing local SOUL service is an internal NOX brain layer, not a separate UI.
# It must not claim direct Windows host / S03 integration until physically tested.
$pycmd=Get-Command py -ErrorAction SilentlyContinue
$python=$null
$argsPrefix=@()
if($pycmd){$python=$pycmd.Source;$argsPrefix=@("-3")}
else {
 $p=Get-Command python -ErrorAction SilentlyContinue
 if($p){$python=$p.Source}
}
if(-not $python){
 Say "Python missing; service HOLD, native NOX still open. Install Python 3 and rerun."
 return
}
$service=Join-Path $source "soul_gpu.py"
$identity=Join-Path $source "identity_behavior.py"
if(-not (Test-Path $identity)){Say "Canonical identity source missing; service HOLD";return}
$env:NOX_ROOT=$root
$env:NOX_SOUL_ROOT=Join-Path $root "soul_gpu"
$oldport=$null
try{$oldport=Invoke-WebRequest -Uri "http://127.0.0.1:18771/health" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop}catch{}
if($oldport){Say "Port 18771 already occupied: not starting second SOUL service";return}
$stdout=Join-Path $logs "soul_service_stdout.log"
$stderr=Join-Path $logs "soul_service_stderr.log"
$argv=@($argsPrefix)+@($service,"serve","--root",$env:NOX_SOUL_ROOT)
Start-Process -FilePath $python -ArgumentList $argv -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WindowStyle Hidden | Out-Null
Start-Sleep -Seconds 3
if(Test-Path (Join-Path $env:NOX_SOUL_ROOT "service.token")){
 Say "SOUL service started with persistent NOX identity; token kept locally."
}else{
 Say "SOUL startup unverified; inspect $stderr. No trained-weights or native integration claim."
}
Say "END: native NOX open if installed; NOX local brain service started if prerequisites passed."
