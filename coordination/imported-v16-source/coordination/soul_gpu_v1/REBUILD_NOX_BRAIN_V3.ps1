# NOX HELION BRAIN REBUILD V3 — canonical storage; never touch Downloads.
$ErrorActionPreference = 'Stop'
$Root = 'C:\NOX_HELION\NOX_NEW'
$Brain = Join-Path $Root 'brain'
$ModelDir = Join-Path $Brain 'intelligence\ollama_models'
$LogDir = Join-Path $Brain 'logs'
$models = @('qwen3:4b-instruct','qwen3:8b','qwen3-embedding:0.6b')
$estimatedBytes = 9500000000L
$minFreeBytes = 60000000000L
New-Item -ItemType Directory -Force -Path $ModelDir,$LogDir,(Join-Path $Brain 'memory'),(Join-Path $Brain 'skills'),(Join-Path $Brain 'intelligence\adapters') | Out-Null
$Log = Join-Path $LogDir ("rebuild-{0}.log" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
function Log($message) { $line = "$(Get-Date -Format s) $message"; Write-Host $line; Add-Content -LiteralPath $Log -Value $line }
Log "NOX Brain Rebuild start. Downloads are NEVER used or scanned."
$drive = [IO.Path]::GetPathRoot($Root)
$free = [IO.DriveInfo]::new($drive).AvailableFreeSpace
if ($free -lt ($estimatedBytes+$minFreeBytes)) { throw "Insufficient free space; need >= 69.5GB free for models + 60GB reserve. Free: $free" }

$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollama) {
  $winget = Get-Command winget -ErrorAction SilentlyContinue
  if (-not $winget) { throw "Ollama and winget not found. Install official Ollama first." }
  Log 'Installing official Ollama using winget'
  & winget install --id Ollama.Ollama --exact --accept-package-agreements --accept-source-agreements
  if ($LASTEXITCODE -ne 0) { throw "Ollama installation failed" }
  $candidatePaths = @("$env:LOCALAPPDATA\Programs\Ollama\ollama.exe","$env:ProgramFiles\Ollama\ollama.exe")
  $path = $candidatePaths | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
  if (-not $path) { $ollama = Get-Command ollama -ErrorAction SilentlyContinue; if ($ollama) { $path=$ollama.Source } }
  if (-not $path) { throw "Installed Ollama not found. Restart PowerShell and rerun." }
} else { $path=$ollama.Source }

# Configure current user and this process. Ollama must be restarted to accept OLLAMA_MODELS.
[Environment]::SetEnvironmentVariable('OLLAMA_MODELS',$ModelDir,'User')
$env:OLLAMA_MODELS = $ModelDir
Log "Canonical Ollama model storage: $ModelDir"
# Gracefully ask existing Ollama to exit; avoid killing unrelated processes.
Get-Process -Name ollama,'ollama app' -ErrorAction SilentlyContinue | ForEach-Object {
  try { $_.CloseMainWindow() | Out-Null } catch {}
}
Start-Sleep -Seconds 3
Get-Process -Name ollama,'ollama app' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
$existing = $false
try { $null=Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2; $existing=$true } catch {}
if ($existing) { throw "An Ollama API server remains active; aborting rather than downloading to an unknown model directory. Shut it down and rerun." }
Log "Starting Ollama with NOX-owned model path"
$server = Start-Process -FilePath $path -ArgumentList 'serve' -PassThru -WindowStyle Hidden
$ready=$false
for($i=0;$i -lt 25;$i++){
  Start-Sleep -Seconds 1
  try { $null=Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2; $ready=$true; break } catch {}
}
if (-not $ready) { throw "Ollama server failed to start. See its local logs." }
foreach($name in $models) {
  $free=[IO.DriveInfo]::new($drive).AvailableFreeSpace
  if ($free -lt $minFreeBytes+2500000000L) { throw "60GB reserve protection: stopping before $name" }
  Log "Pulling $name directly to NOX"
  & $path pull $name
  if ($LASTEXITCODE -ne 0) { throw "Model download failed: $name" }
  & $path show $name | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "Model verification failed: $name" }
  Log "VERIFIED $name"
}
$tags = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 20
$installed = @($tags.models | ForEach-Object {$_.name})
foreach($name in $models) {
  if ($name -notin $installed) { throw "Model not present in API catalog: $name" }
}
# Persist catalog and training state, but do not pretend training happened.
$catalog = [ordered]@{
  created_utc = [DateTime]::UtcNow.ToString('o')
  canonical_path = $ModelDir
  downloads_used = $false
  training_complete = $false
  neural_adapters_trained = $false
  models = @($tags.models | Where-Object { $_.name -in $models } | Select-Object name,model,size,digest)
}
$catalog | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $Brain 'MODEL_CATALOG.json') -Encoding UTF8
Log "SUCCESS: model catalog created at $Brain\MODEL_CATALOG.json"
Log "Models are pretrained; NOX app integration and GPU QLoRA training require separate checks."
