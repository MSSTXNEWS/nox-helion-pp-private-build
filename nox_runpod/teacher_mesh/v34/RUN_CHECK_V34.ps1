$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
python -m unittest brain.tests brain.test_v33 brain.test_v34 brain.test_forge_v34 brain.test_stage_v34 -v
if ($LASTEXITCODE -ne 0) { throw 'NOX V34 failed local tests; do not promote' }
Write-Host 'V34 source verification PASS. Native OneHost/GPU/Windows acceptance remains independent.'
