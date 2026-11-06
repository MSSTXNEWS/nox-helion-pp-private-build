# NOX HELION BRAIN MAX V4 · local Windows orchestrator
# Source in existing PR #162. All permanent assets in C:\NOX_HELION\NOX_NEW.
# instructions_version 0.0.6
$ErrorActionPreference = 'Stop'
$Root = 'C:\NOX_HELION\NOX_NEW'
$Brain = Join-Path $Root 'brain'
$Soul = Join-Path $Root 'soul_gpu'
$ModelHome = Join-Path $Brain 'intelligence\ollama_models'
$Repo = Join-Path $Brain 'source\repo'
$Source = Join-Path $Repo 'coordination\soul_gpu_v1'
$Telemetry = Join-Path $Brain 'telemetry\training.json'
$RunLog = Join-Path $Brain ('logs\BRAIN_MAX_V4_'+(Get-Date -Format yyyyMMdd-HHmmss)+'.log')
$IntelligenceBudget = 70L*1000000000L
$MemoryBudget = 70L*1000000000L
$SkillsBudget = 70L*1000000000L
$ReserveBytes = 60L*1000000000L
$TrainingWorkAllowance = 20L*1000000000L
foreach($p in @($Brain,(Join-Path $Brain 'intelligence'),$ModelHome,(Join-Path $Brain 'intelligence\adapters'),
  (Join-Path $Brain 'memory'),(Join-Path $Brain 'skills'),(Join-Path $Brain 'telemetry'),
  (Join-Path $Brain 'logs'),$Soul)) {
  New-Item -ItemType Directory -Force -Path $p | Out-Null
}
function Say([string]$message) {
  $line = ('{0} {1}' -f (Get-Date -Format 's'),$message)
  Write-Host $line
  Add-Content -LiteralPath $RunLog -Value $line
}
function FolderBytes([string]$path) {
  if(!(Test-Path -LiteralPath $path)){return 0L}
  $sum=0L
  foreach($file in Get-ChildItem -LiteralPath $path -Recurse -File -ErrorAction Stop){
    if(-not ($file.Attributes -band [IO.FileAttributes]::ReparsePoint)){$sum+=$file.Length}
  }
  return $sum
}
function DiskFree { return [IO.DriveInfo]::new(([IO.Path]::GetPathRoot($Root))).AvailableFreeSpace }
function Receipt([string]$status,[hashtable]$details) {
  $j=@{schema='nox.brain.run.v4';status=$status;timestamp=(Get-Date).ToUniversalTime().ToString('o');
       quotas_bytes=@{intelligence=$IntelligenceBudget;memory=$MemoryBudget;skills=$SkillsBudget;free_reserve=$ReserveBytes};
       details=$details}
  $tmp=Join-Path $Brain 'RUN_RECEIPT.json.tmp'
  $dst=Join-Path $Brain 'RUN_RECEIPT.json'
  $j|ConvertTo-Json -Depth 8|Set-Content -LiteralPath $tmp -Encoding UTF8
  Move-Item -LiteralPath $tmp -Destination $dst -Force
}
Say 'BRAIN MAX V4 starting. No Downloads dependency.'
$game=Join-Path $Root 'release\NOX.HELION.exe'
if(Test-Path -LiteralPath $game) {
  try {
    # Existing native host only; no unverified V7 code injection.
    $running=Get-Process -Name 'NOX.HELION' -ErrorAction SilentlyContinue
    if(-not $running){
      Start-Process -FilePath $game -WorkingDirectory (Split-Path $game)
      Say 'Existing NOX.HELION.exe opened (WOW MOTION V7 integration NOT verified)'
    }else{Say 'Existing NOX host already open'}
  }catch{Say ('NOX host launch HOLD: '+$_.Exception.Message)}
}else{Say 'Local NOX.HELION.exe not found; no fake WOW UI launched'}
# Don't overwrite any existing approved datasets, adapter or memory.
$env:NOX_ROOT=$Root
$env:NOX_SOUL_ROOT=$Soul
$env:HF_HOME=Join-Path $Brain 'intelligence\hf_cache'
$env:HF_HUB_CACHE=Join-Path $env:HF_HOME 'hub'
$env:HF_HUB_DISABLE_TELEMETRY='1'
$env:PIP_CACHE_DIR=Join-Path $Brain 'skills\pip_cache'
$env:TMP=Join-Path $Brain 'skills\tmp'
$env:TEMP=$env:TMP
foreach($path in @($env:HF_HOME,$env:PIP_CACHE_DIR,$env:TEMP)){New-Item -ItemType Directory -Force -Path $path | Out-Null}
# Ollama: require current daemon to use NOX-owned manifests; NEVER pull into another profile.
$ollamaCmd=Get-Command ollama -ErrorAction SilentlyContinue
if(-not $ollamaCmd){
  foreach($p in @("$env:LOCALAPPDATA\Programs\Ollama\ollama.exe",
    "$env:ProgramFiles\Ollama\ollama.exe")){
    if(Test-Path $p){$ollamaCmd=Get-Item $p;break}
  }
}
if(-not $ollamaCmd){throw 'Ollama not installed. No weights downloaded; install official Ollama.'}
$ollama=$ollamaCmd.Source
if(-not $ollama){$ollama=$ollamaCmd.FullName}
$env:OLLAMA_MODELS=$ModelHome
[Environment]::SetEnvironmentVariable('OLLAMA_MODELS',$ModelHome,'User')
$live=$false
try{$null=Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 3;$live=$true}catch{}
if(-not $live){
  Say 'Starting Ollama service with NOX canonical model path'
  $null=Start-Process -FilePath $ollama -ArgumentList 'serve' -PassThru -WindowStyle Hidden
  for($i=0;$i -lt 30;$i++){
    Start-Sleep 1
    try{$null=Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2;$live=$true;break}catch{}
  }
}
if(-not $live){throw 'Ollama API failed to start'}
function Tags {return @( (Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 20).models )}
function HasCanonicalManifest([string]$name) {
  $parts=$name.Split(':',2);if($parts.Count -ne 2){return $false}
  return Test-Path -LiteralPath (Join-Path $ModelHome ('manifests\registry.ollama.ai\library\'+$parts[0]+'\'+$parts[1]))
}
# User's installed 3 model tags are reused, no alias copies.
$queue=@(
  @{name='qwen3:4b-instruct';estimated=2.5e9;class='intelligence'},
  @{name='qwen3:8b';estimated=5.2e9;class='intelligence'},
  @{name='qwen3-embedding:0.6b';estimated=0.639e9;class='memory'},
  @{name='qwen3:1.7b';estimated=1.4e9;class='intelligence'},
  @{name='qwen3:14b';estimated=9.3e9;class='intelligence'},
  @{name='qwen3:30b';estimated=19e9;class='intelligence'},
  @{name='qwen3:32b';estimated=20e9;class='intelligence'}
)
$installed=Tags
foreach($item in $queue){
  $name=[string]$item.name
  $present=@($installed|Where-Object{$_.name -eq $name}).Count -gt 0
  if($present -and (HasCanonicalManifest $name)) {Say ("REUSE existing "+$name);continue}
  if($present -and -not (HasCanonicalManifest $name)){
    throw "Ollama sees $name but the NOX canonical manifest is missing. Refusing unsafe duplicate download. Verify daemon OLLAMA_MODELS."
  }
  if((FolderBytes (Join-Path $Brain 'intelligence')) + [long]$item.estimated + 9e9 -gt $IntelligenceBudget){
    Say ("HOLD quota 70GB: "+$name);continue
  }
  if((DiskFree) -lt ($ReserveBytes+[long]$item.estimated+3e9)){
    Say ("HOLD 60GB free reserve: "+$name);continue
  }
  Say ("PULL sequentially "+$name)
  & $ollama pull $name
  if($LASTEXITCODE -ne 0){throw "Ollama pull failed: $name"}
  if(-not (HasCanonicalManifest $name)){throw "Canonical model manifest missing after pull: $name"}
  $installed=Tags
  if(-not @($installed|Where-Object{$_.name -eq $name}).Count){throw "Ollama API does not list downloaded model $name"}
  Say ("VERIFIED "+$name)
}
$tags=Tags
$catalog=[ordered]@{
  created_utc=[DateTime]::UtcNow.ToString('o');source='local-ollama-api';
  canonical_path=$ModelHome;downloads_used=$false;model_budget_bytes=$IntelligenceBudget;
  model_bytes=(FolderBytes $ModelHome);training_claimed=$false;
  models=@($tags|Select-Object name,model,size,digest)
}
$catalog|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $Brain 'MODEL_CATALOG.json') -Encoding UTF8
Say ('MODEL CATALOG real local entries: '+$catalog.models.Count)
if((FolderBytes (Join-Path $Brain 'memory')) -gt $MemoryBudget){throw 'Memory storage quota exceeded'}
if((FolderBytes (Join-Path $Brain 'skills')) -gt $SkillsBudget){throw 'Skills storage quota exceeded'}
# Avoid running independent training processes on the same weights.
$busy=Get-CimInstance Win32_Process -ErrorAction SilentlyContinue|Where-Object{
 $_.CommandLine -match 'train_qlora(_v2)?\.py|nox_lora_weights|SFTTrainer'
}
if($busy){
  Say 'Existing LoRA training process detected — NO duplicate training launched'
  Receipt 'training-already-running' @{models=$catalog.models.Count;processes=@($busy.ProcessId)}
  exit 0
}
$gpuData=$null
if(Get-Command nvidia-smi -ErrorAction SilentlyContinue){
  try{
    $line=(& nvidia-smi --query-gpu=name,memory.total,temperature.gpu --format=csv,noheader,nounits|Select-Object -First 1)
    if($LASTEXITCODE -eq 0 -and $line){$gpuData=$line;Say ('GPU '+$line)}
  }catch{}
}
if(-not $gpuData){
  Say 'CUDA HOLD: no NVIDIA GPU detected. Models ready, training not claimed.'
  Receipt 'cuda-hold' @{models=$catalog.models.Count;telemetry=$Telemetry}
  exit 0
}
$gpuParts=@($gpuData -split ','|ForEach-Object{$_.Trim()})
if([int]$gpuParts[1] -lt 8192){
  Say 'CUDA HOLD: need >=8GB GPU VRAM for selected 4B QLoRA'
  Receipt 'insufficient-vram' @{gpu=$gpuData;models=$catalog.models.Count}
  exit 0
}
$srcTrainer=Join-Path $Source 'train_qlora_v2.py'
if(-not (Test-Path -LiteralPath $srcTrainer)){
  Say ('TRAINER SOURCE MISSING: '+$srcTrainer)
  Receipt 'trainer-missing' @{models=$catalog.models.Count}
  exit 0
}
# Use project-local Python venv; don't modify system Python or Downloads.
$py=Get-Command py -ErrorAction SilentlyContinue
if(-not $py){throw 'Python launcher py not found'}
$venv=Join-Path $Brain 'skills\venv_gpu'
$python=Join-Path $venv 'Scripts\python.exe'
if(-not (Test-Path $python)){
  & py -3.11 -m venv $venv
  if($LASTEXITCODE -ne 0){throw 'Python 3.11 is required for NVIDIA QLoRA'}
}
& $python -m pip install --disable-pip-version-check --upgrade pip
if($LASTEXITCODE -ne 0){throw 'pip update failed'}
& $python -m pip install --disable-pip-version-check torch --index-url https://download.pytorch.org/whl/cu128
if($LASTEXITCODE -ne 0){throw 'PyTorch CUDA install failed'}
& $python -m pip install --disable-pip-version-check transformers peft accelerate bitsandbytes huggingface_hub
if($LASTEXITCODE -ne 0){throw 'QLoRA dependencies install failed'}
& $python -c 'import torch;assert torch.cuda.is_available(), "CUDA torch unavailable"'
if($LASTEXITCODE -ne 0){throw 'CUDA torch unavailable after install; no fake CPU training'}
$permit=Join-Path $Soul 'datasets\owner_approval.json'
$holdout=Join-Path $Soul 'datasets\holdout.jsonl'
if(-not (Test-Path $permit) -or -not (Test-Path $holdout)){
  Say 'TRAINING HOLD: genuine approved datasets/holdout missing. No fabricated data.'
  Receipt 'datasets-required' @{models=$catalog.models.Count;permit=$permit;holdout=$holdout}
  exit 0
}
try{
  $rights=Get-Content -LiteralPath $permit -Raw | ConvertFrom-Json
}catch{throw 'Invalid rights manifest'}
if($rights.owner_approved -ne $true -or $rights.training_allowed -ne $true){
  Say 'TRAINING HOLD: owner approval manifest not authorized'
  Receipt 'rights-hold' @{models=$catalog.models.Count}
  exit 0
}
if((DiskFree) -lt $ReserveBytes+$TrainingWorkAllowance){
  Say 'TRAINING HOLD: preserve 60GB free + 20GB work overhead'
  Receipt 'training-disk-hold' @{models=$catalog.models.Count}
  exit 0
}
$trained=0
for($stage=1;$stage -le 99;$stage++){
  $accepted=Join-Path $Soul ("adapters\stage-"+$stage)
  if(Test-Path (Join-Path $accepted 'TRAINING_EVIDENCE.json')){
    $e=Get-Content (Join-Path $accepted 'TRAINING_EVIDENCE.json') -Raw|ConvertFrom-Json
    if($e.status -ne 'holdout-passed'){throw "Invalid previous stage evidence $stage"}
    Say "REUSE accepted adapter stage $stage"
    continue
  }
  $trainfile=Join-Path $Soul ("blocks\block-"+$stage+"\train.jsonl")
  if(-not (Test-Path $trainfile)){
    Say "NO NEW APPROVED DATA for stage $stage — finish without hallucinating training"
    break
  }
  Say "QLoRA stage $stage, max_steps=1000 GPU fraction=0.75"
  $out=Join-Path $Brain ("logs\train_stage_"+$stage+"_stdout.log")
  $err=Join-Path $Brain ("logs\train_stage_"+$stage+"_stderr.log")
  $argsTrain=@($srcTrainer,'--stage',"$stage",'--root',$Soul,'--max-steps','1000','--max-length','512',
               '--gpu-fraction','0.75')
  $process=Start-Process -FilePath $python -ArgumentList $argsTrain -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
  while(-not $process.HasExited){
    Start-Sleep -Seconds 3
    $process.Refresh()
    if(Test-Path $Telemetry){
      try{
        $t=Get-Content $Telemetry -Raw|ConvertFrom-Json
        if($t.stage -eq $stage){
          $percent=[Math]::Min(100,[int](100*$t.actual_steps/1000))
          Write-Progress -Activity "NOX GPU QLoRA stage $stage" -Status ("{0}/1000 steps · {1}" -f $t.actual_steps,$t.status) -PercentComplete $percent
        }
      }catch{}
    }
  }
  Write-Progress -Activity "NOX GPU QLoRA stage $stage" -Completed
  $process.WaitForExit()
  if($process.ExitCode -ne 0){
    Say "TRAINING HOLD stage $stage; see $err"
    Receipt 'training-stage-hold' @{stage=$stage;stdout=$out;stderr=$err}
    exit 1
  }
  $receipt=Join-Path $accepted 'TRAINING_EVIDENCE.json'
  if(-not(Test-Path $receipt)){throw "Missing training receipt for stage $stage"}
  $proof=Get-Content $receipt -Raw|ConvertFrom-Json
  if($proof.status -ne 'holdout-passed'){throw "Training stage $stage did not pass holdout"}
  $trained++
  Say "QLoRA VERIFIED accepted stage $stage; holdout passed"
}
Receipt 'finished' @{models=$catalog.models.Count;accepted_stages_this_run=$trained;telemetry=$Telemetry;wow_v7_verified=$false}
Say ('DONE; accepted training stages in this run: '+$trained+'; no claim of V7 EXE integration')
