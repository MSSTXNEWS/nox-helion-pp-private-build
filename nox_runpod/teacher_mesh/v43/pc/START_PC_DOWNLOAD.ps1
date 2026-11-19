# NOX V43 — local Windows cold-vault downloader; no services started.
param([switch]$DownloadAll, [string]$Vault='C:\NOX_HELION\MODEL_VAULT')
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
Write-Host 'NOX V43 — verified PC model cold vault (NOX not restarted)'
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw 'Python 3 / py launcher is required. Install Python, rerun this script.'
}
$venv=Join-Path $root '.venv'
if (-not (Test-Path (Join-Path $venv 'Scripts\python.exe'))) {
    py -3 -m venv $venv
}
$python=Join-Path $venv 'Scripts\python.exe'
& $python -m pip install --disable-pip-version-check 'huggingface_hub>=1.2,<2'
if ($LASTEXITCODE -ne 0) { throw 'Dependency install failed' }
if ($DownloadAll) {
    Write-Host 'Downloading ALL FIVE confirmed files/official snapshots sequentially to local disk.'
    & $python (Join-Path $root 'pc\download_models.py') --root $Vault --all --download
} else {
    & $python (Join-Path $root 'pc\download_models.py') --root $Vault
}
if ($LASTEXITCODE -ne 0) { throw 'At least one item is HOLD; see output, previous files kept.' }
