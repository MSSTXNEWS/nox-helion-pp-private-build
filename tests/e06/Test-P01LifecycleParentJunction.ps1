# Original P01 installer lifecycle: native Windows PS5.1 parent-junction regression.
# This fixture never executes an installer, never grants consent and is NOT E07.
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$root=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
$owner=Join-Path $root 'stage/proposals/P01/C09/Installer'
$verify=Join-Path $owner 'Verify-Payload.ps1'
$remove=Join-Path $owner 'Remove-InstalledPayload.ps1'
function Expect-Hold([string]$Script,[hashtable]$Parameters,[string]$Token) {
  $reason=''
  try { & $Script @Parameters | Out-Null } catch { $reason=$_.Exception.Message }
  if (-not $reason.Contains($Token)) { throw "P01_PARENT_TEST_WRONG_HOLD:$Token actual=$reason" }
}
$fixture=Join-Path ([IO.Path]::GetTempPath()) ('NOX-P01-PARENT-'+[guid]::NewGuid().ToString('N'))
$physical=Join-Path $fixture 'physical'
$alias=Join-Path $fixture 'parent-link'
$previousLocal=$env:LOCALAPPDATA
try {
  New-Item -ItemType Directory -Path (Join-Path $physical 'profile/Local/Programs/NOX HELION') -Force | Out-Null
  $junction=New-Item -ItemType Junction -Path $alias -Target $physical -ErrorAction Stop
  if (($junction.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) { throw 'P01_PARENT_TEST_JUNCTION_NOT_CREATED' }
  $env:LOCALAPPDATA=Join-Path $alias 'profile/Local'
  $install=Join-Path $env:LOCALAPPDATA 'Programs/NOX HELION'
  $manifest=Join-Path $install 'payload.sha256.json'
  [IO.File]::WriteAllText($manifest,'{}',[Text.Encoding]::UTF8)
  # Before fix, Verify-Payload skipped parent-link and reached JSON validation.
  Expect-Hold $verify @{Root=$install;Manifest=$manifest} 'reparse or non-directory ancestor'
  # Before fix, uninstall skipped parent-link and reached missing marker.
  Expect-Hold $remove @{InstallRoot=$install} 'P01_UNINSTALL_UNSAFE_PARENT:'
  if (-not (Test-Path -LiteralPath $manifest -PathType Leaf)) { throw 'P01_PARENT_TEST_NOLOSS_FAILURE' }
  'P01_PARENT_JUNCTION_LIFECYCLE_REGRESSION_PASS_NOT_E07'
}
finally {
  $env:LOCALAPPDATA=$previousLocal
  # Remove junction node first, NEVER recurse through its target.
  if (Test-Path -LiteralPath $alias) { [IO.Directory]::Delete($alias) }
  if (-not (Test-Path -LiteralPath $alias) -and (Test-Path -LiteralPath $fixture)) {
    Remove-Item -LiteralPath $fixture -Recurse -Force -ErrorAction Stop
  }
}
