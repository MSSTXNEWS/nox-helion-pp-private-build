$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$source = Join-Path $PSScriptRoot 'NOX_R08_WPF_DIAG_CODE_ONLY.zip.base64'
if (-not (Test-Path -LiteralPath $source)) { throw 'NOX_R08_ARCHIVE_MISSING' }
$text = (Get-Content -LiteralPath $source -Raw).Trim()
$zip = Join-Path $env:RUNNER_TEMP 'nox-r08-code-only.zip'
[IO.File]::WriteAllBytes($zip, [Convert]::FromBase64String($text))
$sha = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
if ($sha -ne 'fbeab580b90930e93f80ea83bea610a034f3411f00f3433b2e688d5ae0d921a9') {
  throw 'NOX_R08_SOURCE_SHA_MISMATCH'
}
$dest = Join-Path $env:RUNNER_TEMP 'nox-r08'
Expand-Archive -LiteralPath $zip -DestinationPath $dest -Force
$root = Join-Path $dest 'R11'
foreach ($file in @('NOX.P01.Shell.csproj','MainWindow.xaml','MainWindow.xaml.cs',
'Contracts/EventV3Bridge.cs','Integration/Pack01HostBridge.cs','Installer/Build-NSIS.ps1','Assets/index.html')) {
  if (-not (Test-Path -LiteralPath (Join-Path $root $file) -PathType Leaf)) { throw "NOX_R08_MISSING:$file" }
}
python (Join-Path $PSScriptRoot 'fix_p05_raw_string.py') $root
python (Join-Path $PSScriptRoot 'fix_r08_stage2.py') $root
python (Join-Path $PSScriptRoot 'fix_r08_stage3.py') $root
python (Join-Path $PSScriptRoot 'fix_r08_stage4.py') $root
if ($LASTEXITCODE -ne 0) { throw 'NOX_R08_PINNED_STAGE4_FAILED' }
if ($LASTEXITCODE -ne 0) { throw 'NOX_R08_PINNED_STAGE3_FAILED' }
if ($LASTEXITCODE -ne 0) { throw 'NOX_R08_PINNED_STAGE2_FAILED' }
if ($LASTEXITCODE -ne 0) { throw 'NOX_R08_PINNED_P05_FIX_FAILED' }
$project = Join-Path $root 'NOX.P01.Shell.csproj'
dotnet restore $project --nologo
if ($LASTEXITCODE -ne 0) { throw 'NOX_R08_DOTNET_RESTORE_FAILED' }
dotnet build $project --configuration Release --no-restore --nologo
if ($LASTEXITCODE -ne 0) { throw 'NOX_R08_WPF_BUILD_FAILED' }
$publish = Join-Path $env:RUNNER_TEMP 'nox-r08-publish'
dotnet publish $project --configuration Release --runtime win-x64 --self-contained true -p:PublishTrimmed=false -p:PublishSingleFile=false --output $publish --nologo
if ($LASTEXITCODE -ne 0) { throw 'NOX_R08_WPF_PUBLISH_FAILED' }
$exe = Join-Path $publish 'NOX.P01.Shell.exe'
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw 'NOX_R08_EXE_MISSING' }
$exeHash = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
$receipt = @{sourceSha256=$sha;exeSha256=$exeHash;buildId=$env:GITHUB_SHA;
 stage='DIAGNOSTIC_ONLY';e07Accepted=$false;sourceVariant='WPF_R08_CODE_ONLY_NO_ORIGINAL_D02_IMAGES'}
$receipt | ConvertTo-Json -Compress | Set-Content -LiteralPath (Join-Path $publish 'DIAGNOSTIC_RECEIPT.json')
Write-Host "NOX_R08_DIAGNOSTIC_SUCCESS EXE_SHA256=$exeHash RELEASE_BLOCKED"
