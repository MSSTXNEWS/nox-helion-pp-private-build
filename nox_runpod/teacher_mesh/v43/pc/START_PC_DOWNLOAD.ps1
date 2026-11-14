# NOX V43 — one existing Windows PC Cold Vault entrypoint. No backend or services.
param(
    [switch]$DownloadAll,
    [switch]$ShowLinks,
    [switch]$VerifyLinks,
    [switch]$DownloadDirect,
    [string[]]$Ids = @(),
    [string]$Vault = 'C:\NOX_HELION\MODEL_VAULT'
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$linkScript = Join-Path $PSScriptRoot 'direct_links.py'
Write-Host 'NOX V43 — PC Cold Vault only (NOX chat, Vast and GPU untouched)'
if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw 'Python 3 launcher (py) is required.'
}
# Link display and SHA metadata verification do not create a venv or install anything.
if ($ShowLinks -or $VerifyLinks) {
    if ($ShowLinks -and $VerifyLinks) { throw 'Choose either -ShowLinks or -VerifyLinks.' }
    $cmd = @('-3', $linkScript)
    if ($VerifyLinks) { $cmd += '--verify-upstream' }
    if ($Ids.Count -gt 0) { $cmd += '--ids'; $cmd += $Ids }
    & py @cmd
    if ($LASTEXITCODE -ne 0) { throw 'At least one model URL or SHA is HOLD.' }
    return
}
if ($DownloadAll -and $DownloadDirect) { throw 'Choose V43 -DownloadAll or direct -DownloadDirect.' }
if ($DownloadDirect -and $Ids.Count -eq 0) { throw 'Direct download needs explicit -Ids.' }
$venv = Join-Path $root '.venv'
$python = Join-Path $venv 'Scripts\python.exe'
if ((-not (Test-Path $python)) -and ($DownloadAll -or $DownloadDirect)) {
    py -3 -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw 'Python venv creation failed.' }
}
if ($DownloadAll -or $DownloadDirect) {
    & $python -m pip install --disable-pip-version-check 'huggingface_hub>=1.2,<2'
    if ($LASTEXITCODE -ne 0) { throw 'Dependency install failed.' }
}
if ($DownloadDirect) {
    & $python $linkScript --root $Vault --ids @Ids --download
} elseif ($DownloadAll) {
    Write-Host 'Opt-in: download existing V43 five models sequentially to Windows Cold Vault.'
    & $python (Join-Path $PSScriptRoot 'download_models.py') --root $Vault --all --download
} else {
    & py -3 (Join-Path $PSScriptRoot 'download_models.py') --root $Vault
}
if ($LASTEXITCODE -ne 0) { throw 'HOLD: see result; NOX and previous files preserved.' }
