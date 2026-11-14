param([switch]$Pull)
$ErrorActionPreference = 'Stop'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = 'C:\NOX_HELION\NOX_NEW\soul_gpu'
if ($env:NOX_SOUL_ROOT) { $Root = $env:NOX_SOUL_ROOT }
New-Item -ItemType Directory -Force -Path $Root | Out-Null
$python = (Get-Command py -ErrorAction SilentlyContinue)
if ($python) { $PyCmd = 'py'; $PyArgs = @('-3') }
else {
  $python = (Get-Command python -ErrorAction SilentlyContinue)
  if (-not $python) { throw 'Python 3 is required; no system changes were made.' }
  $PyCmd = 'python'; $PyArgs = @()
}
$gpu = & $PyCmd @PyArgs "$Here\soul_gpu.py" status --root $Root | ConvertFrom-Json
$gpu | ConvertTo-Json -Depth 5
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollama) { throw 'Ollama executable not found. Install the official Windows Ollama app and re-run.' }
$volume = Get-PSDrive -Name ([System.IO.Path]::GetPathRoot($Root).Substring(0,1))
if ($volume.Free -lt 60000000000) { throw 'Refusing model download: <60 GB free disk reserve' }
$need = @($gpu.fast_model, $gpu.deep_model) | Select-Object -Unique
$installed = (& ollama list) -join "`n"
# Existing Ollama service might be using an external model directory. Never silently
# download outside the verified NOX storage budget; -Pull is explicit and optional.
if ($Pull) {
  if ($env:OLLAMA_MODELS -ne (Join-Path $Root 'ollama_models')) {
    throw "For safe -Pull, set OLLAMA_MODELS=$Root\ollama_models before starting the Ollama daemon. Restart Ollama under that environment."
  }
  New-Item -ItemType Directory -Force -Path $env:OLLAMA_MODELS | Out-Null
  foreach ($model in $need) {
    if ($installed -notmatch [regex]::Escape($model)) {
      Write-Host "Downloading $model to local Ollama storage..."
      & ollama pull $model
      if ($LASTEXITCODE -ne 0) { throw "Ollama download failed: $model" }
    }
  }
}
if (-not $Pull) { Write-Host 'Model download skipped (safe default). To download use -Pull with a verified OLLAMA_MODELS daemon directory.' }
Write-Host "Starting NOX SOUL local service; token at $Root\service.token"
& $PyCmd @PyArgs "$Here\soul_gpu.py" serve --root $Root
