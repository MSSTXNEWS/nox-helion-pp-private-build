param()
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = Join-Path $env:RUNNER_TEMP 'nox-r08/R11'
if (-not (Test-Path -LiteralPath (Join-Path $root 'NOX.P01.Shell.csproj') -PathType Leaf)) {
  throw 'R08_REPRODUCED_SOURCE_MISSING'
}
$builder = Join-Path $root 'Installer/Build-NSIS.ps1'
if (-not (Test-Path -LiteralPath $builder -PathType Leaf)) {
  throw 'R08_ORIGINAL_NSIS_BUILDER_MISSING'
}
$exe = (Get-Command makensis.exe -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty Source)
if (-not $exe) {
  foreach ($p in @('C:/Program Files (x86)/NSIS/makensis.exe', 'C:/Program Files/NSIS/makensis.exe',
                   'C:/tools/nsis/makensis.exe')) {
    if (Test-Path -LiteralPath $p) { $exe = $p; break }
  }
}
if (-not $exe) {
  if (-not (Get-Command choco.exe -ErrorAction SilentlyContinue)) { throw 'NOX_NSIS_TOOL_UNAVAILABLE' }
  & choco install nsis -y --no-progress --limit-output
  if ($LASTEXITCODE -ne 0) { throw 'NOX_NSIS_INSTALL_FAILED' }
  foreach ($p in @('C:/Program Files (x86)/NSIS/makensis.exe', 'C:/Program Files/NSIS/makensis.exe',
                   'C:/tools/nsis/makensis.exe')) {
    if (Test-Path -LiteralPath $p) { $exe = $p; break }
  }
}
if (-not $exe) { throw 'NOX_MAKENSIS_NOT_FOUND' }
$out = Join-Path $env:RUNNER_TEMP 'nox-r08-installer'
& $builder -SourceRoot $root -OutputDir $out -RunId "NOX-R08-WINDOWS-DIAGNOSTIC-$env:GITHUB_RUN_ID" -Makensis $exe -Version '0.1.0-diag'
if ($LASTEXITCODE -ne 0) { throw 'NOX_R08_ORIGINAL_NSIS_FAILED' }
$setup = Join-Path $out 'NOX-HELION-Setup-CANDIDATE.exe'
$receipt = Join-Path $out 'p01-nsis-build-receipt.json'
if (-not ((Test-Path $setup -PathType Leaf) -and (Test-Path $receipt -PathType Leaf))) {
  throw 'NOX_R08_NSIS_ARTIFACT_MISSING'
}
$hash = (Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash.ToLowerInvariant()
$bytes = (Get-Item -LiteralPath $setup).Length
$stamp = [ordered]@{
  runId = "NOX-R08-WINDOWS-DIAGNOSTIC-$env:GITHUB_RUN_ID"
  sourceVariant = 'R08_CODE_ONLY_DIAGNOSTIC'
  fullOriginalD02AssetsIncluded = $false
  installerSha256 = $hash
  installerBytes = $bytes
  releaseAccepted = $false
  e07Accepted = $false
  originalR08ArchiveSha256 = 'fbeab580b90930e93f80ea83bea610a034f3411f00f3433b2e688d5ae0d921a9'
}
$stamp | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $out 'NOX_DIAGNOSTIC_NSIS_RECEIPT.json') -Encoding utf8
Write-Host "NOX_R08_NSIS_DIAGNOSTIC_SUCCESS SETUP_SHA256=$hash SETUP_BYTES=$bytes RELEASE_BLOCKED"
