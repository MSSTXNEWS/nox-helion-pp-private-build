# Source-only Windows regression. Creates no executable binaries and invokes no installer.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'WINDOWS_REQUIRED' }
$savedLocal = $env:LOCALAPPDATA
$fixture = Join-Path ([IO.Path]::GetTempPath()) ('P01-uninstall-test-' + [guid]::NewGuid().ToString('N'))
try {
  $env:LOCALAPPDATA = Join-Path $fixture 'Local'
  $root = Join-Path $env:LOCALAPPDATA 'Programs\NOX HELION'
  New-Item -ItemType Directory -Path $root -Force | Out-Null
  $marker = Join-Path $root 'nox-p01-owned.txt'
  $manifest = Join-Path $root 'payload.sha256.json'
  $file = Join-Path $root 'support.txt'
  [IO.File]::WriteAllText($marker, 'NOXHELION.P01 V16')
  [IO.File]::WriteAllText($file, 'keep me when entrypoint is absent')
  $digest = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash
  $m = [ordered]@{
    schema='NOX_P01_PAYLOAD_SHA256_V1'; entrypoint='NOX.P01.Shell.exe'; runId='R29-A01-UNINSTALL'; version='1.0.0'
    files=@([ordered]@{path='support.txt'; bytes=(Get-Item -LiteralPath $file).Length; sha256=$digest})
  }
  [IO.File]::WriteAllText($manifest, ($m | ConvertTo-Json -Depth 5))
  $metadataHash = (Get-FileHash -LiteralPath $manifest -Algorithm SHA256).Hash
  $caught = $null
  try { & (Join-Path $PSScriptRoot 'Remove-InstalledPayload.ps1') -InstallRoot $root | Out-Null }
  catch { $caught = $_.Exception.Message }
  if ($caught -ne 'P01_UNINSTALL_ENTRYPOINT_UNREGISTERED') { throw "Unexpected refusal: $caught" }
  if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -cne $digest) { throw 'PAYLOAD_CHANGED_ON_REFUSAL' }
  if ((Get-FileHash -LiteralPath $manifest -Algorithm SHA256).Hash -cne $metadataHash) { throw 'METADATA_CHANGED_ON_REFUSAL' }
  if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) { throw 'MARKER_REMOVED_ON_REFUSAL' }
  'P01_UNINSTALL_PARTIAL_MANIFEST_TEST_PASS'
} finally {
  $env:LOCALAPPDATA = $savedLocal
  if (Test-Path -LiteralPath $fixture) { Remove-Item -LiteralPath $fixture -Recurse -Force }
}
