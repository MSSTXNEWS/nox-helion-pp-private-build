param([Parameter(Mandatory)][string]$InstallRoot)
$ErrorActionPreference = 'Stop'
$canon = "$env:LOCALAPPDATA\Programs\NOX HELION"
if ($InstallRoot -ne $canon) { Write-Output 'REMOVE_PATH_NOT_CANONICAL'; exit 2 }
Write-Output 'REMOVE_OK'
exit 0
