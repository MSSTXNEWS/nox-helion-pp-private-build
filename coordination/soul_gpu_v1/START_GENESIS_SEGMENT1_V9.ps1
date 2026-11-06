# NOX GENESIS SEGMENT 1 V9 / no ZIP, no Downloads
$ErrorActionPreference='Stop'
$Root='C:\NOX_HELION\NOX_NEW'
$Brain=Join-Path $Root 'brain'
$Source=Split-Path -Parent $MyInvocation.MyCommand.Path
$Log=Join-Path $Brain 'logs'
$Models=Join-Path $Brain 'intelligence\ollama_models'
$URL='http://127.0.0.1:18872/'
foreach($d in @($Root,$Brain,$Log,(Join-Path $Brain 'telemetry'),$Models,(Join-Path $Brain 'memory'),(Join-Path $Brain 'skills'))){New-Item -ItemType Directory -Force $d|Out-Null}
$env:NOX_ROOT=$Root
$env:NOX_SOUL_ROOT=Join-Path $Root 'soul_gpu'
$env:OLLAMA_MODELS=$Models
$env:HF_HOME=Join-Path $Brain 'intelligence\hf_cache'
$env:PIP_CACHE_DIR=Join-Path $Brain 'skills\pip_cache'
$env:TEMP=Join-Path $Brain 'skills\tmp'
$env:TMP=$env:TEMP
foreach($d in @($env:HF_HOME,$env:PIP_CACHE_DIR,$env:TEMP)){New-Item -ItemType Directory -Force $d|Out-Null}
$py=Get-Command py -ErrorAction SilentlyContinue
if($py){$P=$py.Source;$Prefix=@('-3')}else{$a=Get-Command python -ErrorAction SilentlyContinue;if(!$a){throw 'Python 3 missing'};$P=$a.Source;$Prefix=@()}
foreach($file in @('genesis_v9_audit.py','genesis_segment1.py','identity_behavior.py','soul_gpu.py','genesis_live_cycle.py','forge_genesis_server_v8.py','forge_genesis_v8.html')){
 if(!(Test-Path (Join-Path $Source $file))){throw "Missing source: $file"}
}
# Reconcile old adapters and training first; no duplicate training.
& $P @Prefix (Join-Path $Source 'genesis_v9_audit.py') --root $Root
if($LASTEXITCODE -ne 0){throw 'Training history audit failed'}
$h=$null
try{$h=Invoke-RestMethod ($URL+'api/health') -TimeoutSec 2}catch{}
if($h -and $h.schema -ne 'NOX-GENESIS-FORGE-V8'){throw 'Dashboard port already occupied'}
if(!$h){
 $argsDash=@($Prefix)+@((Join-Path $Source 'forge_genesis_server_v8.py'),'--root',$Root,'--port','18872')
 Start-Process -FilePath $P -ArgumentList $argsDash -WindowStyle Hidden -RedirectStandardOutput (Join-Path $Log 'forge_v9.out') -RedirectStandardError (Join-Path $Log 'forge_v9.err')|Out-Null
 for($i=0;$i -lt 20;$i++){Start-Sleep -Milliseconds 500;try{$h=Invoke-RestMethod ($URL+'api/health') -TimeoutSec 2}catch{};if($h -and $h.schema -eq 'NOX-GENESIS-FORGE-V8'){break}}
}
if(!$h -or $h.schema -ne 'NOX-GENESIS-FORGE-V8'){throw 'FORGE live server failed'}
Start-Process $URL
$cmd=Get-Command ollama -ErrorAction SilentlyContinue
if($cmd){$O=$cmd.Source}else{$O=@("$env:LOCALAPPDATA\Programs\Ollama\ollama.exe","$env:ProgramFiles\Ollama\ollama.exe")|Where-Object{Test-Path $_}|Select-Object -First 1}
if(!$O){throw 'Ollama not installed'}
function Tags{return @((Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 10).models)}
$online=$false
try{$null=Tags;$online=$true}catch{}
if(!$online){
 Start-Process -FilePath $O -ArgumentList 'serve' -WindowStyle Hidden|Out-Null
 for($i=0;$i -lt 25;$i++){Start-Sleep 1;try{$null=Tags;$online=$true;break}catch{}}
}
if(!$online){throw 'Ollama API unavailable'}
# Reject path mismatches, so existing weights are never downloaded twice.
foreach($m in (Tags)){
 if($m.name -in @('qwen3:4b-instruct','qwen3:8b','qwen3-embedding:0.6b')){
  $parts=$m.name.Split(':',2)
  $file=Join-Path $Models ('manifests\registry.ollama.ai\library\'+$parts[0]+'\'+$parts[1])
  if(!(Test-Path $file)){throw ('Ollama model storage mismatch: '+$m.name)}
 }
}
$queue=@(
 @{tag='qwen3:4b-instruct';bytes=2500000000L},
 @{tag='qwen3:8b';bytes=5200000000L},
 @{tag='qwen3-embedding:0.6b';bytes=639000000L},
 @{tag='qwen2.5-coder:7b';bytes=5000000000L}
)
foreach($model in $queue){
 $present=@((Tags)|Where-Object{$_.name -eq $model.tag}).Count -gt 0
 if($present){Write-Host ('NOX REUSE '+$model.tag);continue}
 $free=[IO.DriveInfo]::new('C:\').AvailableFreeSpace
 $used=0L
 Get-ChildItem -LiteralPath (Join-Path $Brain 'intelligence') -Recurse -File -ErrorAction SilentlyContinue|ForEach-Object{$used+=$_.Length}
 if($free -lt (60000000000L+[long]$model.bytes+3000000000L) -or $used+[long]$model.bytes+3000000000L -gt 70000000000L){
  Write-Warning ('NOX quota HOLD '+$model.tag);continue
 }
 & $O pull $model.tag
 if($LASTEXITCODE -ne 0){throw ('Model pull failed '+$model.tag)}
}
$installed=Tags
@{source='local Ollama';models=$installed;training_claimed=$false;time=[DateTime]::UtcNow.ToString('o')}|ConvertTo-Json -Depth 8|Set-Content (Join-Path $Brain 'MODEL_CATALOG.json') -Encoding UTF8
foreach($step in @('init','plan','status')){
 & $P @Prefix (Join-Path $Source 'genesis_segment1.py') $step --root $Root
 if($LASTEXITCODE -ne 0){throw ('Genesis '+$step+' failed')}
}
# Existing NOX EXE only; continuous bounded code candidate loop.
$Native=Join-Path $Root 'release\NOX.HELION.exe'
if((Test-Path $Native) -and !(Get-Process -Name 'NOX.HELION' -ErrorAction SilentlyContinue)){
 Start-Process -FilePath $Native -WorkingDirectory (Split-Path $Native) -WindowStyle Minimized
}
$running=Get-Process -Name 'NOX.HELION' -ErrorAction SilentlyContinue
$workers=@(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue|Where-Object{$_.CommandLine -and $_.CommandLine.Contains('genesis_live_cycle.py') -and $_.CommandLine.Contains($Root)})
if($running -and $workers.Count -eq 0){
 $arguments=@($Prefix)+@((Join-Path $Source 'genesis_live_cycle.py'),'--root',$Root,'--interval','1800','--cycles','0')
 Start-Process -FilePath $P -ArgumentList $arguments -WindowStyle Hidden -RedirectStandardOutput (Join-Path $Log 'genesis_v9.out') -RedirectStandardError (Join-Path $Log 'genesis_v9.err')|Out-Null
}
@{status='GENESIS_PREPARED_TRAINING_HOLD';dashboard=$URL;amd_qlora='NOT_VERIFIED';native_S03='NOT_VERIFIED';native_exe_rebuild='NOT_VERIFIED';temperature_policy='65C pause 180 sec for compatible trainer';historical_audit='brain/telemetry/genesis_v9_audit.json'}|ConvertTo-Json -Depth 5|Set-Content (Join-Path $Brain 'SEGMENT1_V9_RECEIPT.json') -Encoding UTF8
Write-Host ('NOX FORGE LIVE '+$URL)
Start-Process $URL
