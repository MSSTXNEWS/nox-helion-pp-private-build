# NOX HELION / GENESIS WEB V8 · first segment / no ZIP / no Downloads
# Existing NOX host only; no fake LoRA, no automatic EXE replacement.
$ErrorActionPreference='Stop'
$Root='C:\NOX_HELION\NOX_NEW'
$Brain=Join-Path $Root 'brain'
$Dir=Split-Path -Parent $MyInvocation.MyCommand.Path
$Logs=Join-Path $Brain 'logs'
$Tele=Join-Path $Brain 'telemetry'
$Models=Join-Path $Brain 'intelligence\ollama_models'
$Url='http://127.0.0.1:18872/'
foreach($p in @($Root,$Brain,$Logs,$Tele,$Models,(Join-Path $Brain 'memory'),(Join-Path $Brain 'skills'),(Join-Path $Brain 'intelligence\adapters'))){
  New-Item -ItemType Directory -Force -Path $p|Out-Null
}
$Log=Join-Path $Logs ('GENESIS_V8_'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'.log')
function Say([string]$m){
  $line=('{0} {1}' -f (Get-Date -Format s),$m)
  Write-Host $line
  Add-Content -LiteralPath $Log -Value $line
}
function Receipt([string]$state,[hashtable]$details){
  $dst=Join-Path $Brain 'RUN_RECEIPT.json'
  $tmp=$dst+'.tmp'
  [ordered]@{schema='NOX-GENESIS-RUN-V8';status=$state;time=[DateTime]::UtcNow.ToString('o');details=$details;limits=@{intelligence_gb=70;memory_gb=70;skills_gb=70;free_reserve_gb=60;pause_at_c=65;cooling_seconds=180}}|
    ConvertTo-Json -Depth 9|Set-Content -LiteralPath $tmp -Encoding UTF8
  Move-Item -LiteralPath $tmp -Destination $dst -Force
}
function FolderBytes([string]$p){
  if(!(Test-Path -LiteralPath $p)){return 0L}
  $n=0L
  Get-ChildItem -LiteralPath $p -Recurse -File|ForEach-Object{
    if(-not($_.Attributes -band [IO.FileAttributes]::ReparsePoint)){$n+=$_.Length}
  }
  return $n
}
function Manifest([string]$name){
  $a=$name.Split(':',2)
  return ($a.Count -eq 2) -and (Test-Path -LiteralPath (Join-Path $Models ('manifests\registry.ollama.ai\library\'+$a[0]+'\'+$a[1])))
}
function Tags {return @((Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 8).models)}
Say 'NOX GENESIS V8 START · no ZIP / Downloads / redundant copies'
$env:OLLAMA_MODELS=$Models
[Environment]::SetEnvironmentVariable('OLLAMA_MODELS',$Models,'User')
$env:NOX_ROOT=$Root
$env:NOX_SOUL_ROOT=Join-Path $Root 'soul_gpu'
$env:HF_HOME=Join-Path $Brain 'intelligence\hf_cache'
$env:PIP_CACHE_DIR=Join-Path $Brain 'skills\pip_cache'
$env:TEMP=Join-Path $Brain 'skills\tmp'
$env:TMP=$env:TEMP
foreach($p in @($env:HF_HOME,$env:PIP_CACHE_DIR,$env:TEMP)){New-Item -ItemType Directory -Force -Path $p|Out-Null}
$py=Get-Command py -ErrorAction SilentlyContinue
$PyExe=$null
$PyArgs=@()
if($py){$PyExe=$py.Source;$PyArgs=@('-3')}
else{$p=Get-Command python -ErrorAction SilentlyContinue;if($p){$PyExe=$p.Source}}
if(-not $PyExe){Receipt 'PYTHON_MISSING' @{};throw 'Python 3 missing'}
$dashboard=Join-Path $Dir 'forge_genesis_server_v8.py'
$html=Join-Path $Dir 'forge_genesis_v8.html'
$genesis=Join-Path $Dir 'genesis_segment1.py'
$live=Join-Path $Dir 'genesis_live_cycle.py'
$identity=Join-Path $Dir 'identity_behavior.py'
foreach($p in @($dashboard,$html,$genesis,$live,$identity)){
  if(!(Test-Path -LiteralPath $p)){throw ('Missing required source: '+$p)}
}
# Bootstrap dashboard FIRST, verify identity of server so old CORE CHAT is not mistaken for FORGE.
$health=$null
try{$health=Invoke-RestMethod -Uri ($Url+'api/health') -TimeoutSec 2}catch{}
if($health -and $health.schema -ne 'NOX-GENESIS-FORGE-V8'){throw 'Port 18872 occupied by unrelated server'}
if(-not $health){
  $argsDashboard=@($PyArgs)+@($dashboard,'--root',$Root,'--port','18872')
  Start-Process -FilePath $PyExe -ArgumentList $argsDashboard -WindowStyle Hidden -RedirectStandardOutput (Join-Path $Logs 'forge_v8_stdout.log') -RedirectStandardError (Join-Path $Logs 'forge_v8_stderr.log')|Out-Null
  for($i=0;$i -lt 25;$i++){
    Start-Sleep -Milliseconds 500
    try{$health=Invoke-RestMethod -Uri ($Url+'api/health') -TimeoutSec 2}catch{}
    if($health -and $health.schema -eq 'NOX-GENESIS-FORGE-V8'){break}
  }
}
if(-not $health -or $health.schema -ne 'NOX-GENESIS-FORGE-V8'){
  throw 'FORGE V8 failed to start. Inspect forge_v8_stderr.log'
}
Start-Process $Url
Say ('FORGE LIVE WEB OPEN: '+$Url)
Receipt 'WEB_READY' @{url=$Url;training='WAITING_FOR_VERIFIED_TRAINER'}
$ollama=Get-Command ollama -ErrorAction SilentlyContinue
if($ollama){$ollama=$ollama.Source}
else{$ollama=@("$env:LOCALAPPDATA\Programs\Ollama\ollama.exe","$env:ProgramFiles\Ollama\ollama.exe")|Where-Object{Test-Path -LiteralPath $_}|Select-Object -First 1}
if(-not $ollama){Receipt 'OLLAMA_MISSING' @{url=$Url};throw 'Ollama not installed'}
$running=$false
try{$null=Tags;$running=$true}catch{}
if(-not $running){
  Start-Process -FilePath $ollama -ArgumentList 'serve' -WindowStyle Hidden|Out-Null
  for($i=0;$i -lt 25;$i++){Start-Sleep -Seconds 1;try{$null=Tags;$running=$true;break}catch{}}
}
if(-not $running){Receipt 'OLLAMA_API_HOLD' @{url=$Url};throw 'Ollama unavailable'}
$known=@('qwen3:4b-instruct','qwen3:8b','qwen3-embedding:0.6b','qwen2.5-coder:7b')
foreach($x in (Tags)){if($x.name -in $known -and -not (Manifest $x.name)){
  Receipt 'MODEL_STORAGE_MISMATCH' @{model=$x.name}
  throw ('Model present in Ollama but canonical NOX storage differs: '+$x.name)
}}
function SaveCatalog{
  $d=[ordered]@{created_utc=[DateTime]::UtcNow.ToString('o');source='local-ollama-api';canonical_path=$Models;downloads_used=$false;training_claimed=$false;models=@((Tags)|Select-Object name,model,size,digest)}
  $d|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $Brain 'MODEL_CATALOG.json') -Encoding UTF8
}
SaveCatalog
$queue=@(
  @{tag='qwen3:4b-instruct';bytes=2500000000L},
  @{tag='qwen3:8b';bytes=5200000000L},
  @{tag='qwen3-embedding:0.6b';bytes=639000000L},
  @{tag='qwen2.5-coder:7b';bytes=5000000000L}
)
foreach($item in $queue){
  $tag=$item.tag
  if(@((Tags)|Where-Object{$_.name -eq $tag}).Count -gt 0){Say ('REUSE '+$tag);continue}
  $free=[IO.DriveInfo]::new('C:\').AvailableFreeSpace
  if($free -lt (60000000000L+[long]$item.bytes+3000000000L)){Say ('DISK RESERVE HOLD '+$tag);continue}
  if((FolderBytes (Join-Path $Brain 'intelligence'))+[long]$item.bytes+3000000000L -gt 70000000000L){Say ('QUOTA HOLD '+$tag);continue}
  Receipt 'DOWNLOADING' @{model=$tag;url=$Url}
  Say ('PULL '+$tag)
  & $ollama pull $tag
  if($LASTEXITCODE -ne 0 -or -not (Manifest $tag)){throw ('Model pull not verified: '+$tag)}
  SaveCatalog
  Say ('VERIFIED '+$tag)
}
SaveCatalog
foreach($stage in @('init','plan','status')){
  Say ('GENESIS '+$stage)
  & $PyExe @PyArgs $genesis $stage --root $Root
  if($LASTEXITCODE -ne 0){Receipt 'GENESIS_HOLD' @{stage=$stage};throw ('Genesis '+$stage+' failed')}
}
$native=Join-Path $Root 'release\NOX.HELION.exe'
if(-not (Get-Process -Name 'NOX.HELION' -ErrorAction SilentlyContinue) -and (Test-Path -LiteralPath $native)){
  try{
    Start-Process -FilePath $native -WorkingDirectory (Split-Path $native) -WindowStyle Minimized
    Start-Sleep -Seconds 2
    Say 'Existing native NOX EXE started minimized; it is NOT yet bound to new SOUL'
  }catch{Say ('Native EXE HOLD '+$_.Exception.Message)}
}
$workers=@(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue|Where-Object{$_.CommandLine -and $_.CommandLine.Contains('genesis_live_cycle.py') -and $_.CommandLine.Contains($Root)})
if((Get-Process -Name 'NOX.HELION' -ErrorAction SilentlyContinue) -and $workers.Count -eq 0){
  $argsWorker=@($PyArgs)+@($live,'--root',$Root,'--interval','1800','--cycles','0')
  Start-Process -FilePath $PyExe -ArgumentList $argsWorker -WindowStyle Hidden -RedirectStandardOutput (Join-Path $Logs 'genesis_live_stdout.log') -RedirectStandardError (Join-Path $Logs 'genesis_live_stderr.log')|Out-Null
  Say 'GENESIS bounded candidate worker launched; no unreviewed source/EXE modification'
}else{Say 'Worker already running or native NOX process absent'}
$train=Join-Path $Root 'soul_gpu\blocks\block-1\train.jsonl'
$hold=Join-Path $Root 'soul_gpu\datasets\holdout.jsonl'
$permit=Join-Path $Root 'soul_gpu\datasets\owner_approval.json'
$training='CUDA_NO_COMPATIBLE_GPU_OR_SENSOR'
if(Get-Command nvidia-smi -ErrorAction SilentlyContinue){$training='TRAINING_PREFLIGHT_OR_APPROVED_DATA_REQUIRED'}
if(!(Test-Path $train) -or !(Test-Path $hold) -or !(Test-Path $permit)){$training='APPROVED_DATA_OR_HOLDOUT_MISSING'}
# No blind training on AMD or with unknown thermals. Old broken V4 runner never invoked.
Receipt 'GENESIS_READY_WITH_HOLDS' @{url=$Url;training=$training;models=@((Tags)).Count;native_s03='NOT_VERIFIED';native_exe_rebuild='NOT_VERIFIED';worms='PLANNED_AND_REVIEW_CYCLE_ONLY';thermal='65C / 180s, verified sensor mandatory'}
Say ('FORGE LIVE '+$Url+' · training '+$training)
Start-Process $Url
