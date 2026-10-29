# NOX E01 C09 · read-only prerequisites, independent of any second backend.
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if ($env:OS -ne 'Windows_NT') { throw 'P01_PREREQUISITES_WINDOWS_REQUIRED' }
function Probe([string]$Name, [string]$Exe) {
  # C11: count only regular executable application files, not aliases/functions/junctions.
  $cmd=Get-Command $Exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($null -eq $cmd) { return [ordered]@{name=$Name;available=$false;source='PATH';executable=$null} }
  $exePath=[string]$cmd.Source
  if (-not (Test-Path -LiteralPath $exePath -PathType Leaf)) { return [ordered]@{name=$Name;available=$false;source='PATH';executable=$null} }
  $item=Get-Item -LiteralPath $exePath -Force -ErrorAction Stop
  if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { return [ordered]@{name=$Name;available=$false;source='PATH';executable=$null} }
  return [ordered]@{name=$Name;available=$true;source='PATH';executable=$exePath}
}
$items=@(
 (Probe 'Python' 'python.exe'),
 (Probe 'Ollama' 'ollama.exe'),
 (Probe 'Git' 'git.exe'),
 (Probe 'WinGet' 'winget.exe')
)
# Read-only discovery. No versions are fabricated; installed executable != healthy service/model/GPU.
$out=[ordered]@{schema='NOX_P01_PREREQUISITES_V1'; runId=$env:NOX_RUN_ID; evidenceType='LOCAL_PATH_ONLY'; observedUtc=[DateTime]::UtcNow.ToString('o'); requirements=$items; webview2='CHECKED_SEPARATELY'; cuda='NOT_TESTED'; downloadsPerformed=0}
$json=$out|ConvertTo-Json -Depth 6
Write-Output $json
