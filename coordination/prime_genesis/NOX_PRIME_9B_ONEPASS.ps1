# NOX HELION · GENESIS NO-LOSS · one command / exact source version
# Purpose: preserve previous progress, enforce VM-only teachers, inherit full 9B weights.
# INHERITED_UNTRAINED is NOT a verified new 9B training checkpoint.
$ErrorActionPreference = 'Stop'
$brain = 'C:\NOX_HELION\NOX_NEW\brain'
$prime = Join-Path $brain 'prime'
$src = Join-Path $prime 'coordination'
$commit = '37b5fa4c1b141adb0754a5bc768f4b5b72bca138'
$base = "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/$commit/coordination/prime_genesis"
$files = @(
    @{ Name='NOX_PRIME_9B_GENESIS.ps1'; Sha='be3f7df711586a0534d561a40e3844b1d56a8165ff85f5cf85ddaf9c0c1e17b9' },
    @{ Name='NOX_CONTINUITY_POLICY.py'; Sha='6f8c1e89cbec3a1c2b7bb1a03c6092b2c44a82977f37c591f85219384a28382a' }
)
New-Item -ItemType Directory -Force $src | Out-Null
foreach ($spec in $files) {
    $path = Join-Path $src $spec.Name
    $valid = $false
    if (Test-Path $path) {
        $valid = ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ieq $spec.Sha)
    }
    if (!$valid) {
        $part = "$path.part"
        if (Test-Path $part) { Remove-Item -LiteralPath $part -Force }
        Invoke-WebRequest -Uri "$base/$($spec.Name)" -OutFile $part -TimeoutSec 120 -UseBasicParsing
        if ((Get-FileHash -LiteralPath $part -Algorithm SHA256).Hash -ine $spec.Sha) {
            throw "NOX SOURCE INTEGRITY HOLD: $($spec.Name)"
        }
        Move-Item -LiteralPath $part -Destination $path -Force
    }
}
$python = Join-Path $prime 'directml-venv\Scripts\python.exe'
if (!(Test-Path $python)) {
    $python = Join-Path $env:USERPROFILE 'NOX_EXPRESS_AI\NOX_TRAINING\train-venv\Scripts\python.exe'
}
if (!(Test-Path $python)) {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if (!$launcher) { throw 'NOX Python not found' }
    $python = (& py -3 -c 'import sys;print(sys.executable)' | Select-Object -Last 1).Trim()
    if ($LASTEXITCODE -ne 0 -or !(Test-Path $python)) { throw 'Python 3 not available' }
}
$continuity = Join-Path $src 'NOX_CONTINUITY_POLICY.py'
& $python -m py_compile $continuity
if ($LASTEXITCODE -ne 0) { throw 'NOX CONTINUITY SOURCE HOLD' }
Write-Host 'NOX: preserving current trained embryo, existing S03, SAFE70 and creator memory...' -ForegroundColor Cyan
& $python -u $continuity --brain $brain install
if ($LASTEXITCODE -ne 0) { throw 'NOX OPERATIONAL MEMORY HOLD' }

Write-Host 'NOX: inheriting complete Qwen3.5-9B model files to NOX-owned weights...' -ForegroundColor Cyan
$inherit = Join-Path $src 'NOX_PRIME_9B_GENESIS.ps1'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $inherit
if ($LASTEXITCODE -ne 0) { throw 'NOX INHERITANCE HOLD. No existing models deleted.' }

# Reread the actual manifest and prior progress after inheritance.
& $python -u $continuity --brain $brain install
if ($LASTEXITCODE -ne 0) { throw 'NOX CONTINUITY READBACK HOLD' }
Write-Host ''
Write-Host 'NOX FULL-WEIGHT INHERITANCE VERIFIED; NO OLD MODEL DELETED' -ForegroundColor Green
Write-Host 'Foreign teacher host inference: BLOCKED, VM-ONLY policy active.'
Write-Host 'Unknown questions: existing NOX ask falls back to source-linked web retrieval.'
Write-Host '9B weight training and VM teacher execution: NOT YET EXECUTED.'
Write-Host "Research example: & '$python' '$continuity' --brain '$brain' ask 'Qwen3.5 latest training requirements'"