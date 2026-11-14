param([Parameter(Mandatory)][string]$InstallRoot)
$ErrorActionPreference = 'Stop'
if ($InstallRoot -ne "$env:LOCALAPPDATA\Programs\NOX HELION") { Write-Output 'PREFLIGHT_PATH_NOT_CANONICAL'; exit 2 }
Write-Output 'PREFLIGHT_OK'
exit 0
