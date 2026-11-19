# Optional private PC inference endpoint. Does not connect to Vast until an authenticated tunnel exists.
param([string]$Vault='C:\NOX_HELION\MODEL_VAULT')
$ErrorActionPreference='Stop'
$exe=Get-Command 'llama-server' -ErrorAction SilentlyContinue
if (-not $exe) { throw 'llama.cpp is not installed. Install a verified version separately.' }
$ram=[math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB,1)
if ($ram -lt 24) { throw "RAM $ram GB: HOLD. 27B Q4 inference with this RAM is not supported by this launcher. Use cold storage only." }
$flat=Join-Path $Vault 'ROUTER_VERIFIED'
New-Item -ItemType Directory -Path $flat -Force | Out-Null
$ready=0
Get-ChildItem $Vault -Directory | Where-Object { $_.Name -ne 'ROUTER_VERIFIED' } | ForEach-Object {
    $base=$_.FullName
    $receipt=Join-Path $base 'NOX_V43_VERIFIED_RECEIPT.json'
    if (-not (Test-Path $receipt)) { return }
    $data=Get-Content -Path $receipt -Raw | ConvertFrom-Json
    if (-not $data.files -or -not $data.revision) { return }
    Get-ChildItem $base -Filter '*.gguf' -File | ForEach-Object {
        $f=$_
        $match=$data.files | Where-Object { $_.relative_path -eq $f.Name } | Select-Object -First 1
        if (-not $match) { return }
        $expected=[string]$match.sha256
        if ((Get-FileHash -Algorithm SHA256 $f.FullName).Hash.ToLowerInvariant() -ne $expected) { return }
        $link=Join-Path $flat $f.Name
        if (-not (Test-Path $link)) {
            New-Item -ItemType HardLink -Path $link -Value $f.FullName | Out-Null
        }
        $script:ready++
    }
}
if ($ready -eq 0) { throw 'No verified GGUF model to route; download models and check receipts first.' }
Write-Host "Private localhost router: $ready verified models. Only one teacher loaded at once."
& $exe.Source --host '127.0.0.1' --port 18780 --models-dir $flat --models-max 1 --models-memory-margin 2048
