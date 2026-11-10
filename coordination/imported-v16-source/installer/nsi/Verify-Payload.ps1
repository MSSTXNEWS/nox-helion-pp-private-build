param([Parameter(Mandatory)][string]$Root,[Parameter(Mandatory)][string]$Manifest)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $Manifest)) { Write-Output 'VERIFY_MANIFEST_MISSING'; exit 2 }
Write-Output 'VERIFY_OK'
exit 0
