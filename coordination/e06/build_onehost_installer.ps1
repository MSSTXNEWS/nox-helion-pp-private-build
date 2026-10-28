# Owner E06: one WPF UI host with SHA-pinned original Python CLI backend.
# Existing owner P01 NSIS script, Verify-Payload and rollback/uninstall logic reused verbatim.
[CmdletBinding()]
param(
 [Parameter(Mandatory=$true)][string]$SourceRoot,
 [Parameter(Mandatory=$true)][string]$PythonExe,
 [Parameter(Mandatory=$true)][string]$OutputRoot,
 [Parameter(Mandatory=$true)][string]$RunId,
 [Parameter()][string]$ApprovedP01InstallerRoot = '',
 [Parameter()][string]$ApprovedCreativeWebRoot = ''
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if ($RunId -cnotmatch '^[A-Za-z0-9][A-Za-z0-9._:-]{1,127}$') { throw 'E06_INVALID_RUN_ID_HOLD' }
if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitOperatingSystem) { throw 'E06_WINDOWS_X64_REQUIRED' }
# E06 source-identity boundary: forbid junction/symlink ANYWHERE in each
# immutable input ancestry; a pinned leaf hash cannot authenticate its parent.
# Run before the first staging write. Keep output-ancestor guard separate.
function Assert-E06InputPathNoReparse {
  param([Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)][string]$Label)
  $cursor = [IO.Path]::GetFullPath($Path)
  while (![string]::IsNullOrWhiteSpace($cursor)) {
    if (!(Test-Path -LiteralPath $cursor)) { throw "E06_IMMUTABLE_INPUT_MISSING_HOLD:$Label" }
    $entry = Get-Item -LiteralPath $cursor -Force -ErrorAction Stop
    if (($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
      throw "E06_IMMUTABLE_INPUT_REPARSE_ANCESTOR_HOLD:$Label"
    }
    $parent = [IO.Path]::GetDirectoryName($cursor)
    if ([string]::IsNullOrWhiteSpace($parent) -or $parent -ieq $cursor) { break }
    $cursor = $parent
  }
}
Assert-E06InputPathNoReparse -Path $SourceRoot -Label 'SOURCE_ROOT'
Assert-E06InputPathNoReparse -Path $PythonExe -Label 'PINNED_PYTHON_EXE'
$source=(Resolve-Path -LiteralPath $SourceRoot).Path
$original=(Resolve-Path -LiteralPath $PythonExe).Path
$exeDigest='4e488372cf3f6410d268a7ef72b3e4b359a7a3e6642c7a16ac2e6f7eb06fc5f3'
if ((Get-FileHash -LiteralPath $original -Algorithm SHA256).Hash.ToLowerInvariant() -cne $exeDigest) { throw 'PYTHON_ORIGINAL_BINARY_SHA_HOLD' }
$project=Join-Path $source 'NOX.P01.Shell.csproj'
$installer=Join-Path $source 'Installer'

# Owner P01 C13 commit 8e42bb15aecbee8412c342b0e9049b6cce044297 is read-only.
# Exact Linux LF and Windows CRLF copies are both pinned; never silently normalize or overwrite.
# Use -ApprovedP01InstallerRoot if the older staged installer contains stale WebView2 prereqs.
$approvedRoot = if ([string]::IsNullOrWhiteSpace($ApprovedP01InstallerRoot)) {
  $installer
} else {
  (Resolve-Path -LiteralPath $ApprovedP01InstallerRoot -ErrorAction Stop).Path
}
Assert-E06InputPathNoReparse -Path $(if ([string]::IsNullOrWhiteSpace($ApprovedP01InstallerRoot)) { $installer } else { $ApprovedP01InstallerRoot }) -Label 'P01_INSTALLER_ROOT'
# E06 NO-LOSS: P01 installer owner root is immutable input, never an output folder.
$approvedCanon = [IO.Path]::GetFullPath($approvedRoot).TrimEnd('\')
$outputCandidateCanon = [IO.Path]::GetFullPath($OutputRoot).TrimEnd('\')
if ($approvedCanon -ieq $outputCandidateCanon -or
    $outputCandidateCanon.StartsWith($approvedCanon + '\',[StringComparison]::OrdinalIgnoreCase) -or
    $approvedCanon.StartsWith($outputCandidateCanon + '\',[StringComparison]::OrdinalIgnoreCase)) {
  throw 'NO_LOSS_APPROVED_P01_OUTPUT_PATH_OVERLAP'
}
# Existing output-parent junctions may evade lexical path-prefix checks.
$parentToCheck = [IO.Path]::GetDirectoryName($outputCandidateCanon)
while (![string]::IsNullOrWhiteSpace($parentToCheck)) {
  if (Test-Path -LiteralPath $parentToCheck) {
    $parentInfo = Get-Item -LiteralPath $parentToCheck -Force
    if (($parentInfo.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
      throw 'NO_LOSS_OUTPUT_PARENT_REPARSE_HOLD'
    }
  }
  $nextParent = [IO.Path]::GetDirectoryName($parentToCheck)
  if ([string]::IsNullOrWhiteSpace($nextParent) -or $nextParent -ieq $parentToCheck) { break }
  $parentToCheck = $nextParent
}

$approvedHashes = [ordered]@{
  'Preflight-InstallPath.ps1' = @('1c84e8def6d8a9ce6dbe3aa4dc7a4013f54836065f541925334bbf46bf502008','cd5c0fa3eb3218b2438d5f88c40010461e5e3f291b4f2a21e757fa863e14e91a')
  'Verify-Payload.ps1' = @('5f54ba06e9f5e2e156e571b8ab2d3338d507bad880867dcbcc9cad769738d736','91bcff06212f82c9b551ea4744142163e4e9b00c837034823356349f01dc3192')
  'Remove-InstalledPayload.ps1' = @('dc4c7d537e18b8a107b27ab199ab9df4116fcf7a33f06b8058ce0b6edb8acc0e','5de22d37c8c21a6cc9527e97008a0ad4e57128bc90f273a12bef440903f266f7')
  'NOX-HELION-Setup.nsi' = @('3b21accfd088050fc57629aa60ac61024a10307c12731a4c0f0ef41edf1fd1bc','03d679804412a7113d08b90e9321879ad4d282cc497dca620cbe8c9c6b52d9db')
}
$approvedPreflightHashes = [ordered]@{}
foreach ($name in $approvedHashes.Keys) {
  $candidate = Join-Path $approvedRoot $name
  if (!(Test-Path -LiteralPath $candidate -PathType Leaf)) { throw "P01_APPROVED_SCRIPT_MISSING:$name" }
  $item = Get-Item -LiteralPath $candidate -Force
  if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "P01_SCRIPT_REPARSE_HOLD:$name" }
  $digest = (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLowerInvariant()
  if (@($approvedHashes[$name]) -cnotcontains $digest) { throw "P01_OWNER_PREIMAGE_SHA_HOLD:$name" }
  $approvedPreflightHashes[$name] = $digest
}
$verifyScript = Join-Path $approvedRoot 'Verify-Payload.ps1'
$preflightScript = Join-Path $approvedRoot 'Preflight-InstallPath.ps1'
$removeScript = Join-Path $approvedRoot 'Remove-InstalledPayload.ps1'
$nsisScript = Join-Path $approvedRoot 'NOX-HELION-Setup.nsi'
# Original P01 Verify-Payload requires strictly numeric version, not 16.0.0-rc.
$appVersion = '16.0.0'
$sourceCanon = [IO.Path]::GetFullPath($source).TrimEnd('\')
$outputCanon = [IO.Path]::GetFullPath($OutputRoot).TrimEnd('\')
if ($sourceCanon -ieq $outputCanon -or
    $outputCanon.StartsWith($sourceCanon + '\',[StringComparison]::OrdinalIgnoreCase) -or
    $sourceCanon.StartsWith($outputCanon + '\',[StringComparison]::OrdinalIgnoreCase)) {
  throw 'NO_LOSS_SOURCE_OUTPUT_PATH_OVERLAP'
}
if (!(Test-Path -LiteralPath $project -PathType Leaf)) { throw 'EXISTING_WPF_SOURCE_MISSING' }
if (!(Test-Path -LiteralPath $nsisScript -PathType Leaf)) { throw 'ORIGINAL_NSIS_OWNER_SOURCE_MISSING' }

# E06 fail-closed admission: the existing WPF projector maps
# https://nox.local/creative/theater.html onto the original Assets directory.
# An absent/unpinned theater cannot be shipped as a working cinema route.
if ([string]::IsNullOrWhiteSpace($ApprovedCreativeWebRoot)) { throw 'E06_APPROVED_THEATER_WEB_ROOT_REQUIRED_HOLD' }
Assert-E06InputPathNoReparse -Path $ApprovedCreativeWebRoot -Label 'CREATIVE_WEB_ROOT'
$creativeRoot=(Resolve-Path -LiteralPath $ApprovedCreativeWebRoot -ErrorAction Stop).Path
$creativeInfo=Get-Item -LiteralPath $creativeRoot -Force
if (!$creativeInfo.PSIsContainer -or ($creativeInfo.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'E06_THEATER_SOURCE_DIRECTORY_HOLD' }
$creativeCanon=[IO.Path]::GetFullPath($creativeRoot).TrimEnd('\')
if ($creativeCanon -ieq $outputCanon -or
    $creativeCanon.StartsWith($outputCanon + '\',[StringComparison]::OrdinalIgnoreCase) -or
    $outputCanon.StartsWith($creativeCanon + '\',[StringComparison]::OrdinalIgnoreCase)) {
  throw 'NO_LOSS_CREATIVE_OUTPUT_PATH_OVERLAP'
}
$creativeHashes=[ordered]@{
 'theater.html'='59823e151104200c6ba64d2b56ff6ea1a4a1f72a97bcf12f75b749fc05468f11'
 'theater.js'='62562ac81c5ff565e5e9c584c9201a26809bb390155a23b6c5cfee0948da6b42'
}
foreach ($name in $creativeHashes.Keys) {
  $from=Join-Path $creativeRoot $name
  if (!(Test-Path -LiteralPath $from -PathType Leaf)) { throw "E06_THEATER_SOURCE_MISSING:$name" }
  $sourceItem=Get-Item -LiteralPath $from -Force
  if (($sourceItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
      (Get-FileHash -LiteralPath $from -Algorithm SHA256).Hash.ToLowerInvariant() -cne $creativeHashes[$name]) {
    throw "E06_THEATER_SOURCE_SHA_HOLD:$name"
  }
}

if (Test-Path -LiteralPath $OutputRoot) { throw 'OUTPUT_ALREADY_EXISTS_NO_OVERWRITE' }
New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
$out=(Resolve-Path $OutputRoot).Path
$payload=Join-Path $out 'payload'
# One native UI process, original Python runtime invoked ONLY by fixed --diagnose, not auto-started.
& dotnet publish $project -c Release -r win-x64 --self-contained true -p:PublishSingleFile=false -p:PublishTrimmed=false -o $payload --nologo --verbosity minimal
if ($LASTEXITCODE -ne 0) { throw 'ONEHOST_WPF_SELFCONTAINED_PUBLISH_HOLD' }
if (!(Test-Path -LiteralPath (Join-Path $payload 'NOX.P01.Shell.exe'))) { throw 'WPF_ENTRYPOINT_MISSING' }
$backend=Join-Path $payload 'Backend'
New-Item -ItemType Directory -Path $backend -Force | Out-Null
Copy-Item -LiteralPath $original -Destination (Join-Path $backend 'NOX_HELION_PRIVATE_CANDIDATE.exe')
if ((Get-FileHash (Join-Path $backend 'NOX_HELION_PRIVATE_CANDIDATE.exe') -Algorithm SHA256).Hash.ToLowerInvariant() -cne $exeDigest) { throw 'PINNED_PYTHON_COPY_HOLD' }
# Approved four original D02 images remain unchanged and present.
$assets=@{
  'home.png'='382c1069afcaaaed11c319796f2c553d2bd977d7e46c68ecd7d55af26e132a4a'
  'menu.png'='4c73d137e6d25f496abb006dbb8af08b1fe272d2f935c5006f0f42b6fd9992b9'
  'core01.png'='343e5c73539358fe2c086706b4155cc0f9cd9702fcd40a98b4aab130585bec97'
  'menu_sections.png'='7d181604f913cf9956c173c14da3dc7fd0238c389322896588cec4407b4024a4'
}
foreach($name in $assets.Keys) {
 $file=Join-Path $payload ('Assets\'+$name)
 if (!(Test-Path -LiteralPath $file -PathType Leaf)) { throw "D02_APPROVED_ASSET_MISSING:$name" }
 if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -cne $assets[$name]) { throw "D02_ASSET_SHA_HOLD:$name" }
}

# Stage ONLY the two hash-locked E06 theater resources. Original D02 binaries
# remain byte-identical. Never overwrite a foreign WPF asset or follow a reparse.
$assetsDest=Join-Path $payload 'Assets'
if (!(Test-Path -LiteralPath $assetsDest -PathType Container) -or
    ((Get-Item -LiteralPath $assetsDest -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
  throw 'E06_ORIGINAL_ASSET_ROOT_HOLD'
}
$creativeDest=Join-Path $assetsDest 'creative'
if (Test-Path -LiteralPath $creativeDest) {
  $targetDir=Get-Item -LiteralPath $creativeDest -Force
  if (!$targetDir.PSIsContainer -or ($targetDir.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'E06_THEATER_DEST_DIRECTORY_HOLD' }
} else { New-Item -ItemType Directory -Path $creativeDest | Out-Null }
foreach ($name in $creativeHashes.Keys) {
  $from=Join-Path $creativeRoot $name
  if (!(Test-Path -LiteralPath $from -PathType Leaf) -or
      ((Get-Item -LiteralPath $from -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
      (Get-FileHash -LiteralPath $from -Algorithm SHA256).Hash.ToLowerInvariant() -cne $creativeHashes[$name]) { throw "E06_THEATER_SOURCE_CHANGED_DURING_BUILD_HOLD:$name" }
  $to=Join-Path $creativeDest $name
  if (Test-Path -LiteralPath $to) {
    if (!(Test-Path -LiteralPath $to -PathType Leaf)) { throw "E06_THEATER_DEST_CONFLICT_HOLD:$name" }
    $destItem=Get-Item -LiteralPath $to -Force
    if (($destItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
        (Get-FileHash -LiteralPath $to -Algorithm SHA256).Hash.ToLowerInvariant() -cne $creativeHashes[$name]) { throw "E06_THEATER_DEST_CONFLICT_HOLD:$name" }
  } else { Copy-Item -LiteralPath $from -Destination $to -ErrorAction Stop }
  if ((Get-FileHash -LiteralPath $to -Algorithm SHA256).Hash.ToLowerInvariant() -cne $creativeHashes[$name]) { throw "E06_THEATER_STAGED_SHA_HOLD:$name" }
}

# Include the existing program files in the conservative NSIS manifest.
$entries=@(Get-ChildItem -LiteralPath $payload -File -Recurse | Sort-Object FullName | ForEach-Object {
  if (($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'NO_REPARSE_PAYLOAD' }
  $relative=$_.FullName.Substring($payload.Length).TrimStart('\')
  [ordered]@{path=$relative.Replace('\','/');bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
})
$manifest=[ordered]@{schema='NOX_P01_PAYLOAD_SHA256_V1';entrypoint='NOX.P01.Shell.exe';taskId='NOX-V16-E06-EXPRESS-ONEHOST';runId=$RunId;version=$appVersion;files=$entries}
$manifestPath=Join-Path $payload 'payload.sha256.json'
[IO.File]::WriteAllText($manifestPath,($manifest | ConvertTo-Json -Depth 7),(New-Object System.Text.UTF8Encoding($false)))
& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $verifyScript -Root $payload -Manifest $manifestPath
if ($LASTEXITCODE -ne 0) { throw 'ORIGINAL_NSIS_PAYLOAD_SHA_GATE_HOLD' }
# Save exact manifest bytes only AFTER the original P01 verifier accepts them.
$manifestAdmissionSha256=(Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant()
$makensis=Get-Command 'makensis.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $makensis) {
  if (-not (Get-Command choco -ErrorAction SilentlyContinue)) { throw 'NSIS_NOT_INSTALLED_AND_NO_TRUSTED_PACKAGE_MANAGER' }
  & choco install nsis --version=3.11 --no-progress -y
  if ($LASTEXITCODE -ne 0) { throw 'PINNED_NSIS_INSTALL_HOLD' }
  $candidates=@('C:\Program Files (x86)\NSIS\makensis.exe','C:\Program Files\NSIS\makensis.exe')
  $resolved=$candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
  if (!$resolved) { throw 'NSIS_BINARY_UNAVAILABLE_AFTER_PINNED_INSTALL' }
  $makensis=Get-Item -LiteralPath $resolved
}
$makensisPath = if ($makensis -is [System.IO.FileInfo]) { $makensis.FullName } else { $makensis.Source }
if ([string]::IsNullOrWhiteSpace($makensisPath) -or !(Test-Path -LiteralPath $makensisPath -PathType Leaf)) { throw 'NSIS_BINARY_PATH_HOLD' }
# E06 R06: preserve exact approved P01 script bytes across staging and compilation.
# Both CRLF/LF variants are permitted at admission, but never a mid-build swap.
foreach ($name in $approvedHashes.Keys) {
  $candidate = Join-Path $approvedRoot $name
  if (!(Test-Path -LiteralPath $candidate -PathType Leaf)) { throw "P01_OWNER_SOURCE_DISAPPEARED_BEFORE_NSIS_HOLD:$name" }
  $item = Get-Item -LiteralPath $candidate -Force
  if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "P01_OWNER_SOURCE_REPARSE_BEFORE_NSIS_HOLD:$name" }
  $digest = (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($digest -cne $approvedPreflightHashes[$name]) { throw "P01_OWNER_SOURCE_MUTATED_DURING_BUILD_HOLD:$name" }
}
# E06 R07 final payload gate: no unmanifested reparse directories, no swapped
# manifest and no changed staged file between original admission and makensis.
# Preserve P01 verifier and fail closed; no second installer/host is introduced.
if (!(Test-Path -LiteralPath $payload -PathType Container)) { throw 'E06_PAYLOAD_ROOT_MISSING_BEFORE_NSIS_HOLD' }
if (((Get-Item -LiteralPath $payload -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
  throw 'E06_PAYLOAD_ROOT_REPARSE_BEFORE_NSIS_HOLD'
}
foreach ($directory in @(Get-ChildItem -LiteralPath $payload -Directory -Recurse -Force -ErrorAction Stop)) {
  if (($directory.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw 'E06_PAYLOAD_DIRECTORY_REPARSE_BEFORE_NSIS_HOLD'
  }
}
if (!(Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw 'E06_PAYLOAD_MANIFEST_MISSING_BEFORE_NSIS_HOLD' }
if (((Get-Item -LiteralPath $manifestPath -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
  throw 'E06_PAYLOAD_MANIFEST_REPARSE_BEFORE_NSIS_HOLD'
}
if ((Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $manifestAdmissionSha256) {
  throw 'E06_PAYLOAD_MANIFEST_CHANGED_BEFORE_NSIS_HOLD'
}
& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $verifyScript -Root $payload -Manifest $manifestPath
if ($LASTEXITCODE -ne 0) { throw 'E06_PAYLOAD_FINAL_VERIFY_BEFORE_NSIS_HOLD' }
$setup=Join-Path $out 'NOX-HELION-V16-DIAGNOSTIC-SETUP.exe'
& $makensisPath /V2 "/DPAYLOAD_DIR=$payload" "/DVERIFY_SCRIPT=$verifyScript" "/DPREFLIGHT_SCRIPT=$preflightScript" "/DREMOVE_SCRIPT=$removeScript" "/DOUTPUT_SETUP=$setup" "/DAPP_VERSION=$appVersion" $nsisScript
if ($LASTEXITCODE -ne 0 -or !(Test-Path -LiteralPath $setup -PathType Leaf)) { throw 'EXISTING_OWNER_NSIS_COMPILER_HOLD' }
$sha=(Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash.ToLowerInvariant()
$wpf=Join-Path $payload 'NOX.P01.Shell.exe'
$receipt=[ordered]@{
 schema='NOX-E06-ONEHOST-DIAGNOSTIC-NSIS-v1';run_id=$RunId;owner=6;
 wpf_exe_sha256=(Get-FileHash -LiteralPath $wpf -Algorithm SHA256).Hash.ToLowerInvariant();
 python_backend_sha256=$exeDigest;installer_sha256=$sha;installer_bytes=(Get-Item $setup).Length;
 payload_manifest_sha256=(Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant();
 original_D02_sha256=$assets;creative_web_sha256=$creativeHashes;creative_route='https://nox.local/creative/theater.html';
 status='WINDOWS_INSTALLER_CANDIDATE_NOT_E07_ACCEPTED';real_ollama_gpu_sip_tested=$false;
 one_visible_host=$true;native_bridge_scope='ORIGINAL_PYTHON_READ_ONLY_DIAGNOSE';
 installer_lifecycle_tested=$false;release_accepted=$false;owner_1_5_accepted=$false
}
$receiptPath=Join-Path $out 'ONEHOST_DIAGNOSTIC_RECEIPT.json'
[IO.File]::WriteAllText($receiptPath,($receipt | ConvertTo-Json -Depth 9),(New-Object System.Text.UTF8Encoding($false)))
Write-Host "E06_ONEHOST_NSIS_CANDIDATE_BUILT $sha"
