# Run on authorized Windows x64 runner only; publish self-contained WPF first.
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$SourceRoot,
  [Parameter(Mandatory=$true)][string]$OutputDir,
  [string]$RunId = 'P01-UNSET',
  [string]$Makensis = 'makensis.exe',
  [string]$Version = '0.1.0',
  [switch]$SkipPublish
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$installer = $PSScriptRoot
$project = Join-Path $SourceRoot 'NOX.P01.Shell.csproj'
if (-not (Test-Path -LiteralPath $project -PathType Leaf)) { throw 'P01_SOURCE_PROJECT_MISSING' }
if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitOperatingSystem) { throw 'P01_WINDOWS_X64_REQUIRED' }
if (-not (Get-Command $Makensis -ErrorAction SilentlyContinue)) { throw 'P01_MAKENSIS_NOT_AVAILABLE' }
# Never publish into reparse folders or onto a pre-existing payload tree.
$sourceCanonical=[IO.Path]::GetFullPath($SourceRoot).TrimEnd('\')
$rootCandidate=[IO.Path]::GetFullPath($OutputDir)
if ($rootCandidate -ieq $sourceCanonical -or $rootCandidate.StartsWith($sourceCanonical+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'P01_BUILD_OUTPUT_INSIDE_SOURCE' }
$walk=$rootCandidate
while ($walk) {
  if (Test-Path -LiteralPath $walk) {
    $node=Get-Item -LiteralPath $walk -Force -ErrorAction Stop
    if (-not $node.PSIsContainer -or (($node.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) { throw "P01_BUILD_UNSAFE_OUTPUT_PARENT:$walk" }
  }
  $next=[IO.Path]::GetDirectoryName($walk)
  if ($next -eq $walk) { break }
  $walk=$next
}
New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
$root = [IO.Path]::GetFullPath($OutputDir)
$payload = Join-Path $root 'payload'
if (Test-Path -LiteralPath $payload) { throw 'P01_OUTPUT_PAYLOAD_EXISTS_USE_FRESH_DIR' }
New-Item -ItemType Directory -Path $payload | Out-Null
if (-not $SkipPublish) {
  & dotnet publish $project --configuration Release --runtime win-x64 --self-contained true --output $payload -p:PublishTrimmed=false -p:PublishSingleFile=false -p:RestorePackagesWithLockFile=true
  if ($LASTEXITCODE -ne 0) { throw 'P01_DOTNET_PUBLISH_FAILED' }
} else {
  throw 'P01_SKIP_PUBLISH_DISABLED_FOR_RELEASE_SAFETY'
}
if (-not (Test-Path -LiteralPath (Join-Path $payload 'NOX.P01.Shell.exe'))) { throw 'P01_PUBLISHED_EXE_MISSING' }
$files = @(Get-ChildItem -LiteralPath $payload -Recurse -File | Sort-Object FullName | ForEach-Object {
  $relative = $_.FullName.Substring($payload.Length).TrimStart('\')
  if ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "P01_REPARSE_POINT:$relative" }
  if ($relative -match '[:*?"<>|]' -or $relative -match '(^|[\\/])\.\.([\\/]|$)') { throw "P01_UNSAFE_PUBLISH_PATH:$relative" }
  [ordered]@{path=$relative.Replace('\','/');bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
})
$manifest = [ordered]@{ schema='NOX_P01_PAYLOAD_SHA256_V1'; entrypoint='NOX.P01.Shell.exe'; taskId='V16-E01-P01-NSIS'; runId=$RunId; version=$Version; files=$files }
$manifestPath = Join-Path $payload 'payload.sha256.json'
[IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 7), (New-Object System.Text.UTF8Encoding($false)))
& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $installer 'Verify-Payload.ps1') -Root $payload -Manifest $manifestPath
if ($LASTEXITCODE -ne 0) { throw 'P01_LOCAL_MANIFEST_SELFTEST_FAILED' }
$setup = Join-Path $root 'NOX-HELION-Setup-CANDIDATE.exe'
& $Makensis /V2 "/DPAYLOAD_DIR=$payload" "/DVERIFY_SCRIPT=$(Join-Path $installer 'Verify-Payload.ps1')" "/DPREFLIGHT_SCRIPT=$(Join-Path $installer 'Preflight-InstallPath.ps1')" "/DREMOVE_SCRIPT=$(Join-Path $installer 'Remove-InstalledPayload.ps1')" "/DOUTPUT_SETUP=$setup" "/DAPP_VERSION=$Version" (Join-Path $installer 'NOX-HELION-Setup.nsi')
if ($LASTEXITCODE -ne 0) { throw 'P01_MAKENSIS_FAILED' }
$receipt = [ordered]@{
  schema='NOX_P01_NSIS_BUILD_RECEIPT_V1'; taskId='V16-E01-P01-NSIS';runId=$RunId;sourceRoot=[IO.Path]::GetFullPath($SourceRoot);
  payloadManifestSha256=(Get-FileHash $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant();
  setupSha256=(Get-FileHash $setup -Algorithm SHA256).Hash.ToLowerInvariant();
  setupBytes=(Get-Item $setup).Length;
  stage='CANDIDATE_UNVERIFIED_E07';
}
$receipt | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $root 'p01-nsis-build-receipt.json') -Encoding UTF8
Write-Host 'P01 NSIS candidate built; native install/update/rollback/E07 gates remain separate.'
