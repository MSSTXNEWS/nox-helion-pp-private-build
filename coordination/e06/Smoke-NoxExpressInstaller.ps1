# NOX V16 · disposable Windows-runner INSTALL/VERIFY/UNINSTALL smoke.
# This script NEVER runs on the user's PC and NEVER removes an unowned install.
[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$Installer,
  [Parameter(Mandatory=$true)][string]$BuildReceipt,
  [Parameter(Mandatory=$true)][string]$EvidencePath
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$state='NOT_STARTED'
$report=[ordered]@{
  schema='NOX_V16_INSTALL_LIFECYCLE_DIAGNOSTIC_V1'
  originalRunId='40611023212'
  stage='NOT_STARTED'
  installerVerified=$false
  payloadVerified=$false
  originalD02Verified=$false
  originalPythonInert=$false
  nativeOneHostConnected=$false
  nativeInstallAndUninstallVerified=$false
  finalProductAccepted=$false
  errorCode=$null
  installerSha256=$null
  payloadFiles=0
}
function Require([bool]$ok,[string]$code) {
  if (-not $ok) {throw $code}
}
function IsReparse([object]$item) {
  return (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)
}
function WriteEvidence {
  $folder=[IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($EvidencePath))
  if (-not (Test-Path -LiteralPath $folder -PathType Container)) {
    New-Item -ItemType Directory -Path $folder -Force | Out-Null
  }
  $report.stage=$state
  $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $EvidencePath -Encoding UTF8
  $read=Get-Content -LiteralPath $EvidencePath -Raw -Encoding UTF8 | ConvertFrom-Json
  Require ($read.schema -ceq 'NOX_V16_INSTALL_LIFECYCLE_DIAGNOSTIC_V1') 'NOX_SMOKE_READBACK_INVALID'
}
$root=[IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs\NOX HELION')).TrimEnd('\')
try {
  Require ([IO.Path]::IsPathRooted($root) -and $root.StartsWith(
    [IO.Path]::GetFullPath($env:LOCALAPPDATA).TrimEnd('\')+'\',
    [StringComparison]::OrdinalIgnoreCase)) 'NOX_SMOKE_INSTALL_PATH_NOT_USER_SCOPED'
  foreach($path in @($root,"$root.__p01_stage","$root.__p01_previous","$root.__p01_rollback_saved")) {
    Require (-not (Test-Path -LiteralPath $path)) 'NOX_SMOKE_PREEXISTING_INSTALL_OR_BACKUP_HOLD'
  }
  Require (Test-Path -LiteralPath $Installer -PathType Leaf) 'NOX_SMOKE_INSTALLER_MISSING'
  Require (Test-Path -LiteralPath $BuildReceipt -PathType Leaf) 'NOX_SMOKE_RECEIPT_MISSING'
  $receipt=Get-Content -LiteralPath $BuildReceipt -Raw -Encoding UTF8 | ConvertFrom-Json
  Require ($receipt.schema -ceq 'NOX_EXPRESS_BLOCK1_COMBINED_DIAGNOSTIC_V1') 'NOX_SMOKE_RECEIPT_SCHEMA'
  Require ([string]$receipt.buildRunId -ceq '40611023212') 'NOX_SMOKE_WRONG_BUILD_RUN'
  Require ($receipt.packagedInstallerIsDiagnostic -eq $true -and
           $receipt.oneHostBridgeVerified -eq $false -and
           $receipt.productComplete -eq $false -and
           $receipt.e07IndependentFinalAccepted -eq $false) 'NOX_SMOKE_MISLABELED_RELEASE'
  Require ($receipt.originalPythonSourceSha256 -ceq 'ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a') 'NOX_SMOKE_ORIGINAL_SOURCE_DRIFT'
  $actual=(Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash.ToLowerInvariant()
  $report.installerSha256=$actual
  Require ($actual -ceq ([string]$receipt.installerSetupSha256).ToLowerInvariant()) 'NOX_SMOKE_INSTALLER_SHA_MISMATCH'
  Require ((Get-Item -LiteralPath $Installer).Length -eq [long]$receipt.installerSetupBytes) 'NOX_SMOKE_INSTALLER_BYTES_MISMATCH'
  $report.installerVerified=$true
  $state='INSTALLING'
  $process=Start-Process -FilePath ([IO.Path]::GetFullPath($Installer)) -ArgumentList '/S' -Wait -PassThru -WindowStyle Hidden
  Require ($process.ExitCode -eq 0) "NOX_SMOKE_INSTALL_EXIT_$($process.ExitCode)"
  Require (Test-Path -LiteralPath $root -PathType Container) 'NOX_SMOKE_INSTALL_ROOT_NOT_CREATED'
  Require (-not (IsReparse (Get-Item -LiteralPath $root))) 'NOX_SMOKE_REPARSE_INSTALL_ROOT'
  Require (Test-Path -LiteralPath (Join-Path $root 'nox-p01-owned.txt') -PathType Leaf) 'NOX_SMOKE_OWNER_MARKER_MISSING'
  Require ((Get-Content -LiteralPath (Join-Path $root 'nox-p01-owned.txt') -Raw).Trim() -ceq 'NOXHELION.P01 V16') 'NOX_SMOKE_OWNER_MARKER_INVALID'
  Require (Test-Path -LiteralPath (Join-Path $root 'payload.sha256.json') -PathType Leaf) 'NOX_SMOKE_INSTALL_MANIFEST_MISSING'
  Require (Test-Path -LiteralPath (Join-Path $root 'Uninstall.exe') -PathType Leaf) 'NOX_SMOKE_UNINSTALLER_MISSING'
  $manifest=Get-Content -LiteralPath (Join-Path $root 'payload.sha256.json') -Raw -Encoding UTF8 | ConvertFrom-Json
  Require ($manifest.schema -ceq 'NOX_P01_PAYLOAD_SHA256_V1' -and
           $manifest.entrypoint -ceq 'NOX.P01.Shell.exe' -and
           @($manifest.files).Count -eq [int]$receipt.stagedFiles) 'NOX_SMOKE_MANIFEST_DRIFT'
  $registered=New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
  foreach($row in $manifest.files){
    $rel=[string]$row.path
    Require ($rel -notmatch '(^|[\\/])\.\.([\\/]|$)' -and
             $rel -notmatch '[:*"<>|?]' -and
             -not [IO.Path]::IsPathRooted($rel)) 'NOX_SMOKE_UNSAFE_MANIFEST_PATH'
    Require ($registered.Add($rel.Replace('/','\'))) 'NOX_SMOKE_DUPLICATE_PAYLOAD_PATH'
    $file=[IO.Path]::GetFullPath((Join-Path $root $rel))
    Require ($file.StartsWith($root+'\',[StringComparison]::OrdinalIgnoreCase)) 'NOX_SMOKE_PAYLOAD_PATH_ESCAPES_ROOT'
    Require (Test-Path -LiteralPath $file -PathType Leaf) 'NOX_SMOKE_PAYLOAD_FILE_MISSING'
    $item=Get-Item -LiteralPath $file
    Require (-not (IsReparse $item)) 'NOX_SMOKE_PAYLOAD_IS_REPARSE'
    Require ($item.Length -eq [long]$row.bytes) 'NOX_SMOKE_PAYLOAD_LENGTH_DRIFT'
    Require ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -ceq
      ([string]$row.sha256).ToLowerInvariant()) 'NOX_SMOKE_PAYLOAD_SHA_DRIFT'
  }
  $files=@(Get-ChildItem -LiteralPath $root -Recurse -Force -File)
  foreach($file in $files) {
    $rel=$file.FullName.Substring($root.Length+1)
    if($rel -in @('Uninstall.exe','payload.sha256.json','nox-p01-owned.txt')) {continue}
    Require ($registered.Contains($rel)) 'NOX_SMOKE_UNEXPECTED_INSTALLED_FILE'
  }
  Require ($files.Count -eq $registered.Count+3) 'NOX_SMOKE_INSTALLED_FILE_COUNT_DRIFT'
  $report.payloadVerified=$true
  $report.payloadFiles=$registered.Count
  $state='VERIFYING_APPROVED_ART'
  $d02=@{
    'Assets\home.png'='382c1069afcaaaed11c319796f2c553d2bd977d7e46c68ecd7d55af26e132a4a'
    'Assets\menu.png'='4c73d137e6d25f496abb006dbb8af08b1fe272d2f935c5006f0f42b6fd9992b9'
    'Assets\core01.png'='343e5c73539358fe2c086706b4155cc0f9cd9702fcd40a98b4aab130585bec97'
    'Assets\menu_sections.png'='7d181604f913cf9956c173c14da3dc7fd0238c389322896588cec4407b4024a4'
  }
  foreach($k in $d02.Keys){
    $p=Join-Path $root $k
    Require (Test-Path -LiteralPath $p -PathType Leaf) 'NOX_SMOKE_APPROVED_D02_ASSET_MISSING'
    Require ((Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant() -ceq $d02[$k]) 'NOX_SMOKE_APPROVED_D02_SHA_DRIFT'
  }
  $report.originalD02Verified=$true
  # These are merely preserved binaries, not an authorized connected Python host.
  $legacy=Join-Path $root 'Legacy'
  Require (Test-Path -LiteralPath (Join-Path $legacy 'NOX_HELION_PRIVATE_CANDIDATE.exe') -PathType Leaf) 'NOX_SMOKE_LEGACY_PYTHON_MISSING'
  Require (Test-Path -LiteralPath (Join-Path $legacy 'NOX_HELION_BACKGROUND_CANDIDATE.exe') -PathType Leaf) 'NOX_SMOKE_LEGACY_BACKGROUND_MISSING'
  Require (Test-Path -LiteralPath (Join-Path $legacy 'NOT_CONNECTED_TO_WPF.txt') -PathType Leaf) 'NOX_SMOKE_MISSING_PYTHON_INERT_WARNING'
  $report.originalPythonInert=$true
  $state='UNINSTALLING'
  $uninstaller=Join-Path $root 'Uninstall.exe'
  $process=Start-Process -FilePath $uninstaller -ArgumentList '/S' -Wait -PassThru -WindowStyle Hidden
  Require ($process.ExitCode -eq 0) "NOX_SMOKE_UNINSTALL_EXIT_$($process.ExitCode)"
  Require (-not (Test-Path -LiteralPath (Join-Path $root 'NOX.P01.Shell.exe'))) 'NOX_SMOKE_UNINSTALL_PAYLOAD_REMAINS'
  Require (-not (Test-Path -LiteralPath (Join-Path $root 'nox-p01-owned.txt'))) 'NOX_SMOKE_UNINSTALL_MARKER_REMAINS'
  Require (-not (Test-Path -LiteralPath $root)) 'NOX_SMOKE_UNINSTALL_ROOT_REMAINS'
  $report.nativeInstallAndUninstallVerified=$true
  $state='INSTALL_VERIFY_UNINSTALL_PASS'
  Write-Host 'NOX_V16_INSTALL_LIFECYCLE_PASS: diagnostic setup install; 29 SHA-proven files; D02 byte exact; Python inert; safe uninstall.'
} catch {
  $report.errorCode=([string]$_.Exception.Message).Split([Environment]::NewLine)[0]
  $state='INSTALL_VERIFY_UNINSTALL_HOLD'
  Write-Host ('NOX_V16_INSTALL_LIFECYCLE_HOLD: '+$report.errorCode)
  throw
} finally {
  WriteEvidence
}
