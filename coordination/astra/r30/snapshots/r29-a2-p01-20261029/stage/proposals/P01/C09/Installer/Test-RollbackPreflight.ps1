# Native source-only regression. No NSIS build, application install or release CI.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'WINDOWS_REQUIRED' }
$savedLocal = $env:LOCALAPPDATA
$fixture = Join-Path ([IO.Path]::GetTempPath()) ('P01-rollback-test-' + [guid]::NewGuid().ToString('N'))
$script = Join-Path $PSScriptRoot 'Preflight-InstallPath.ps1'
$junction = $null
function Assert-Refused([string]$Root, [string]$ErrorCode) {
  $caught = $null
  try { & $script -InstallRoot $Root -PathOnly | Out-Null } catch { $caught = $_.Exception.Message }
  if (-not $caught -or -not $caught.StartsWith($ErrorCode)) { throw "Expected $ErrorCode, got $caught" }
}
try {
  $env:LOCALAPPDATA = Join-Path $fixture 'Local'
  $root = Join-Path $env:LOCALAPPDATA 'Programs\NOX HELION'
  New-Item -ItemType Directory -Path $root -Force | Out-Null
  $marker = Join-Path $root 'nox-p01-owned.txt'
  Set-Content -LiteralPath $marker -Value 'NOXHELION.P01 V16' -Encoding UTF8
  $result = & $script -InstallRoot $root -PathOnly
  if ($result -ne 'P01_PATH_PREFLIGHT_PASS') { throw 'PATH_PREFLIGHT_FAILED' }
  Set-Content -LiteralPath $marker -Value 'not installer owned' -Encoding UTF8
  Assert-Refused $root 'P01_INSTALL_MARKER_INVALID'
  Set-Content -LiteralPath $marker -Value 'NOXHELION.P01 V16' -Encoding UTF8
  Assert-Refused (Join-Path $fixture 'Other') 'P01_INSTALL_ROOT_INVALID'
  $programs = Join-Path $env:LOCALAPPDATA 'Programs'
  $realPrograms = Join-Path $fixture 'RealPrograms'
  Move-Item -LiteralPath $programs -Destination $realPrograms
  $junction = $programs
  New-Item -ItemType Junction -Path $junction -Target $realPrograms | Out-Null
  Assert-Refused $root 'P01_INSTALL_REPARSE_ANCESTOR'
  'P01_ROLLBACK_PREFLIGHT_TEST_PASS: valid, marker, wrong-root, ancestor-junction'
} finally {
  $env:LOCALAPPDATA = $savedLocal
  # Remove the junction itself before recursively deleting this disposable fixture.
  if ($junction -and (Test-Path -LiteralPath $junction)) { [IO.Directory]::Delete($junction) }
  if (Test-Path -LiteralPath $fixture) { Remove-Item -LiteralPath $fixture -Recurse -Force }
}
