# Owner E06: one WPF UI host with SHA-pinned original Python CLI backend.
# Existing owner P01 NSIS script, Verify-Payload and rollback/uninstall logic reused verbatim.
[CmdletBinding()]
param(
 [Parameter(Mandatory=$true)][string]$SourceRoot,
 [Parameter(Mandatory=$true)][string]$PythonExe,
 [Parameter(Mandatory=$true)][string]$OutputRoot,
 [Parameter(Mandatory=$true)][string]$RunId,
 [string]$CreativeSourceRoot='',
 [string]$WowSourceRoot='',
 [string]$PersonaBundlePath=''
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
# R48 T06: fail closed before touching source/output or invoking any tool.
# Strict .NET anchors prevent newline suffix bypass and filesystem path injection.
if ($RunId -cnotmatch '\A[A-Za-z0-9][A-Za-z0-9._:-]{1,127}\z') {
  throw 'E06_BUILD_INVALID_RUN_ID'
}
# Reject redirected input/output ancestors BEFORE resolve or publish (source gate).
# This does not attest Windows races/ACLs; native acceptance remains HOLD.
function Assert-E06PlainPathAncestors {
  param([Parameter(Mandatory=$true)][string]$Candidate,
        [Parameter(Mandatory=$true)][string]$Scope)
  $cursor=[IO.Path]::GetFullPath($Candidate)
  while ($true) {
    try {
      $attributes=[IO.File]::GetAttributes($cursor)
      if (($attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "E06_${Scope}_REPARSE_ANCESTOR_HOLD"
      }
    }
    catch [IO.FileNotFoundException] { }
    catch [IO.DirectoryNotFoundException] { }
    $parent=[IO.Directory]::GetParent($cursor)
    if ($null -eq $parent) { break }
    $cursor=$parent.FullName
  }
}
Assert-E06PlainPathAncestors -Candidate $SourceRoot -Scope 'SOURCE'
Assert-E06PlainPathAncestors -Candidate $PythonExe -Scope 'PYTHON'
Assert-E06PlainPathAncestors -Candidate $OutputRoot -Scope 'OUTPUT'
$source=(Resolve-Path -LiteralPath $SourceRoot).Path
$original=(Resolve-Path -LiteralPath $PythonExe).Path
$exeDigest='4e488372cf3f6410d268a7ef72b3e4b359a7a3e6642c7a16ac2e6f7eb06fc5f3'
if ((Get-FileHash -LiteralPath $original -Algorithm SHA256).Hash.ToLowerInvariant() -cne $exeDigest) { throw 'PYTHON_ORIGINAL_BINARY_SHA_HOLD' }
$project=Join-Path $source 'NOX.P01.Shell.csproj'
$installer=Join-Path $source 'Installer'
Assert-E06PlainPathAncestors -Candidate $project -Scope 'WPF_PROJECT'
Assert-E06PlainPathAncestors -Candidate (Join-Path $installer 'NOX-HELION-Setup.nsi') -Scope 'NSIS_OWNER'
if (!(Test-Path -LiteralPath $project -PathType Leaf)) { throw 'EXISTING_WPF_SOURCE_MISSING' }
if (!(Test-Path -LiteralPath (Join-Path $installer 'NOX-HELION-Setup.nsi') -PathType Leaf)) { throw 'ORIGINAL_NSIS_OWNER_SOURCE_MISSING' }
# The original diagnostic builder keeps its existing behavior unless BOTH visual
# sources are explicitly supplied. Never silently use an old D02 donor.
$wantsCreative= -not [string]::IsNullOrWhiteSpace($CreativeSourceRoot)
$wantsWow= -not [string]::IsNullOrWhiteSpace($WowSourceRoot)
if ($wantsCreative -ne $wantsWow) { throw 'D02_VISUAL_STAGE_PAIR_REQUIRED' }
$wantsPersona= -not [string]::IsNullOrWhiteSpace($PersonaBundlePath)
if ($wantsPersona -and !$wantsCreative) { throw 'PERSONA_REQUIRES_ORIGINAL_VISUAL_STAGE' }
# R48 T06: require preinstalled NSIS before D02 staging or WPF publish.
$makensis=Get-Command 'makensis.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $makensis) {
  # Never install software or run a package manager as a build-script side effect.
  # T10 SOURCE_READY and separately approved build stage remain upstream gates.
  $candidates=@('C:\Program Files (x86)\NSIS\makensis.exe','C:\Program Files\NSIS\makensis.exe')
  $resolved=$candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
  if (!$resolved) { throw 'NSIS_PREINSTALLED_BINARY_REQUIRED_NO_AUTO_INSTALL' }
  $makensis=Get-Item -LiteralPath $resolved -ErrorAction Stop
}
$makensisPath = if ($makensis -is [System.IO.FileInfo]) { $makensis.FullName } else { $makensis.Source }
if ([string]::IsNullOrWhiteSpace($makensisPath) -or !(Test-Path -LiteralPath $makensisPath -PathType Leaf)) { throw 'NSIS_BINARY_PATH_HOLD' }
# Require the existing .NET 8 SDK before any disposable visual staging or publish.
# This is read-only discovery, not a package-manager install.
$dotnetSdk = Get-Command dotnet.exe -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $dotnetSdk) { throw 'E06_DOTNET8_SDK_REQUIRED_PRECHECK' }
$installedSdks = @(& $dotnetSdk.Source --list-sdks 2>$null)
if ($LASTEXITCODE -ne 0 -or
    @($installedSdks | Where-Object { $_ -match '^8\.' }).Count -eq 0) {
  throw 'E06_DOTNET8_SDK_REQUIRED_PRECHECK'
}
$visualStage='NOT_REQUESTED'
$wowReceiptPath=$null
$personaReceiptPath=$null
if ($wantsCreative) {
  # Mutating visual stages operate only on stage_p01.py's disposable source,
  # never on historical archives, pristine HOME or the Git checkout source.
  $lockPath=Join-Path (Split-Path -Parent $source) 'source_lock.json'
  Assert-E06PlainPathAncestors -Candidate $lockPath -Scope 'SOURCELOCK'
  if (!(Test-Path -LiteralPath $lockPath -PathType Leaf)) { throw 'D02_DISPOSABLE_SOURCELOCK_REQUIRED' }
  $lock=Get-Content -LiteralPath $lockPath -Raw -Encoding UTF8 | ConvertFrom-Json
  if ($lock.schema -cne 'NOX-E06-P01-WINDOWS-DIAGNOSTIC-SOURCE-v1' -or
      $lock.source_unchanged -ne $true -or $lock.release_accepted -ne $false) {
    throw 'D02_DISPOSABLE_SOURCELOCK_INVALID'
  }
  Assert-E06PlainPathAncestors -Candidate $CreativeSourceRoot -Scope 'CREATIVE'
  Assert-E06PlainPathAncestors -Candidate $WowSourceRoot -Scope 'WOW'
  $creative=(Resolve-Path -LiteralPath $CreativeSourceRoot).Path
  $wow=(Resolve-Path -LiteralPath $WowSourceRoot).Path
  $creativeScript=Join-Path $creative 'stage_creative.py'
  $wowScript=Join-Path $wow 'stage_wow200.py'
  foreach ($file in @($creativeScript,$wowScript)) {
    if (!(Test-Path -LiteralPath $file -PathType Leaf)) { throw 'D02_OWNER_STAGING_SCRIPT_MISSING' }
  }
  $git=Get-Command 'git.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
  $py=Get-Command 'python.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
  if (!$git -or !$py) { throw 'D02_PINNED_GIT_PYTHON_TOOLS_REQUIRED' }
  $creativeScriptBlob=(& $git.Source hash-object -- $creativeScript).Trim().ToLowerInvariant()
  $wowScriptBlob=(& $git.Source hash-object -- $wowScript).Trim().ToLowerInvariant()
  if ($creativeScriptBlob -cne '9d6b22198bd57362477afa1a7132c982793c1a64' -or
      $wowScriptBlob -cne 'a3b25309edd4e86962d2fb4687f96b887d4dca87') {
    throw 'D02_PINNED_STAGE_SCRIPT_SHA_HOLD'
  }
  if (Test-Path -LiteralPath (Join-Path $source 'Assets/creative')) {
    throw 'D02_CREATIVE_STAGE_ALREADY_PRESENT'
  }
  & $py.Source $creativeScript $source $creative
  if ($LASTEXITCODE -ne 0) { throw 'D02_CREATIVE_STAGE_FAILED' }
  & $py.Source $wowScript $source $wow
  if ($LASTEXITCODE -ne 0) { throw 'D02_WOW_STAGE_FAILED' }
  $wowReceiptPath=Join-Path (Split-Path -Parent $source) 'WOW200_STAGE_RECEIPT.json'
  if (!(Test-Path -LiteralPath $wowReceiptPath -PathType Leaf)) { throw 'D02_WOW_STAGE_RECEIPT_MISSING' }
  $wowReceipt=Get-Content -LiteralPath $wowReceiptPath -Raw -Encoding UTF8 | ConvertFrom-Json
  if ($wowReceipt.count -ne 65 -or $wowReceipt.active_d02_engine -cne 'OWNER1_PR144_PINNED' -or
      $wowReceipt.legacy_d02_runtime_imported -ne $false -or
      $wowReceipt.pack01_catalog_routes -ne 50 -or
      $wowReceipt.source_only -ne $true -or $wowReceipt.release_accepted -ne $false) {
    throw 'D02_WOW_STAGE_RECEIPT_REJECTED'
  }
  # Exactly the bytes the HOME runtime actually imports; previous PR30 stays
  # in a different, unimported legacy directory inside the disposable stage.
  $ownerRepoRoot=Split-Path -Parent (Split-Path -Parent $wow)
  foreach ($name in @('nox-cinema.mjs','nox-cinema.css')) {
    $canonical=Join-Path $ownerRepoRoot ('proposals/NOX-CINEMA-FX/' + $name)
    $active=Join-Path $source ('Assets/creative/wow200/proposals/NOX-CINEMA-FX/' + $name)
    $legacy=Join-Path $source ('Assets/creative/wow200/legacy/d02-pr30/' + $name)
    if (!(Test-Path -LiteralPath $active -PathType Leaf) -or
        !(Test-Path -LiteralPath $canonical -PathType Leaf) -or
        !(Test-Path -LiteralPath $legacy -PathType Leaf)) { throw 'D02_ACTIVE_OR_ARCHIVE_MISSING' }
    if ((Get-FileHash -LiteralPath $active -Algorithm SHA256).Hash -cne
        (Get-FileHash -LiteralPath $canonical -Algorithm SHA256).Hash) {
      throw 'D02_ACTIVE_ENGINE_BYTES_MISMATCH'
    }
  }
  $homeHtml=Get-Content -LiteralPath (Join-Path $source 'Assets/index.html') -Raw -Encoding UTF8
  $homeScriptCount=([regex]::Matches($homeHtml,[regex]::Escape('creative/wow200/runtime/home-scene.mjs'))).Count
  if ($homeScriptCount -ne 1) {
    throw 'D02_HOME_LOADER_DUPLICATE_OR_ABSENT'
  }
  if ($wantsPersona) {
    # Optional, exact SHA pinned local owner media. No network or synthetic faces.
    $personaScript=Join-Path $creative 'stage_persona_media.py'
    if (!(Test-Path -LiteralPath $personaScript -PathType Leaf)) { throw 'PERSONA_OWNER_STAGE_SCRIPT_MISSING' }
    $personaBlob=(& $git.Source hash-object -- $personaScript).Trim().ToLowerInvariant()
    if ($personaBlob -cne '5eed031e9f8dc5fb9c829e0dfa0668014b7eda36') { throw 'PERSONA_STAGE_SCRIPT_SHA_HOLD' }
    Assert-E06PlainPathAncestors -Candidate $PersonaBundlePath -Scope 'PERSONA'
    $personaBundle=(Resolve-Path -LiteralPath $PersonaBundlePath -ErrorAction Stop).Path
    $personaFile=Get-Item -LiteralPath $personaBundle -Force
    if ($personaFile.PSIsContainer -or
        ($personaFile.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'PERSONA_BUNDLE_NOT_REGULAR_HOLD' }
    if ((Get-FileHash -LiteralPath $personaBundle -Algorithm SHA256).Hash.ToLowerInvariant() -cne
        '9abc124ce1a543417afcd2a08097c5d72b5901a10830869cf495fa7045330ec7') {
      throw 'PERSONA_APPROVED_BUNDLE_SHA_HOLD'
    }
    & $py.Source $personaScript $source $personaBundle
    if ($LASTEXITCODE -ne 0) { throw 'PERSONA_OWNER_STAGE_HOLD' }
    $personaReceiptPath=Join-Path (Split-Path -Parent $source) 'PERSONA_STAGE_RECEIPT.json'
    if (!(Test-Path -LiteralPath $personaReceiptPath -PathType Leaf)) { throw 'PERSONA_STAGE_RECEIPT_MISSING' }
    $personaProof=Get-Content -LiteralPath $personaReceiptPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($personaProof.schema -cne 'NOX_PERSONA_STAGED_R15' -or
        $personaProof.active_count -ne 4 -or $personaProof.identity_candidate_hold -ne 1 -or
        $personaProof.media_files -ne 8 -or $personaProof.native_windows_accepted -ne $false -or
        $personaProof.source_bundle_sha256 -cne '9abc124ce1a543417afcd2a08097c5d72b5901a10830869cf495fa7045330ec7') {
      throw 'PERSONA_APPROVED_STAGE_RECEIPT_HOLD'
    }
  }
  $visualStage='D02_OWNER1_CANONICAL_STAGE_SHA_VERIFIED_SOURCE_ONLY'
}
if (Test-Path -LiteralPath $OutputRoot) { throw 'OUTPUT_ALREADY_EXISTS_NO_OVERWRITE' }
New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
Assert-E06PlainPathAncestors -Candidate $OutputRoot -Scope 'OUTPUT_POST_CREATE'
$out=(Resolve-Path $OutputRoot).Path
$payload=Join-Path $out 'payload'
# One native UI process, original Python runtime invoked ONLY by fixed --diagnose, not auto-started.
& dotnet publish $project -c Release -r win-x64 --self-contained true -p:PublishSingleFile=false -p:PublishTrimmed=false -o $payload --nologo --verbosity minimal
if ($LASTEXITCODE -ne 0) { throw 'ONEHOST_WPF_SELFCONTAINED_PUBLISH_HOLD' }
if (!(Test-Path -LiteralPath (Join-Path $payload 'NOX.P01.Shell.exe'))) { throw 'WPF_ENTRYPOINT_MISSING' }
# Do not trust dotnet publish to copy newly staged visual Content assets.
# PRECHECK every file; copy only canonical disposable R11 visual bytes, never an
# unknown prior renderer or unrelated original owner asset.
$visualPayloadRecords=@()
$visualPayloadReceipt=$null
if ($wantsCreative) {
  $indexEntries=@($lock.artifacts | Where-Object { $_.path -ceq 'R11/Assets/index.html' })
  if ($indexEntries.Count -ne 1 -or
      [string]::IsNullOrWhiteSpace([string]$indexEntries[0].sha256)) {
    throw 'D02_ORIGINAL_INDEX_SHA_NOT_IN_SOURCELOCK'
  }
  $originalIndexSha=([string]$indexEntries[0].sha256).ToLowerInvariant()
  $stagedCreative=Join-Path $source 'Assets/creative'
  $stagedIndex=Join-Path $source 'Assets/index.html'
  $publishedAssets=Join-Path $payload 'Assets'
  if (!(Test-Path -LiteralPath $stagedCreative -PathType Container) -or
      !(Test-Path -LiteralPath $stagedIndex -PathType Leaf) -or
      !(Test-Path -LiteralPath $publishedAssets -PathType Container)) {
    throw 'D02_STAGED_OR_PUBLISHED_ASSETS_MISSING'
  }
  $stagedFiles=@(Get-Item -LiteralPath $stagedIndex)
  $stagedFiles+=@(Get-ChildItem -LiteralPath $stagedCreative -File -Recurse -Force)
  foreach ($node in @(Get-Item -LiteralPath $stagedCreative) + @(Get-ChildItem -LiteralPath $stagedCreative -Recurse -Force)) {
    if (($node.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
      throw 'D02_STAGED_VISUAL_REPARSE_HOLD'
    }
  }
  $publishedCreative=Join-Path $publishedAssets 'creative'
  if (Test-Path -LiteralPath $publishedCreative) {
    foreach ($node in @(Get-Item -LiteralPath $publishedCreative) + @(Get-ChildItem -LiteralPath $publishedCreative -Recurse -Force)) {
      if (($node.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw 'D02_PUBLISHED_VISUAL_REPARSE_HOLD'
      }
      if (!$node.PSIsContainer) {
        $relative=$node.FullName.Substring($payload.Length+1)
        if (!(Test-Path -LiteralPath (Join-Path $source $relative) -PathType Leaf)) {
          throw "D02_UNEXPECTED_PUBLISHED_VISUAL_FILE:$relative"
        }
      }
    }
  }
  # Preflight all collisions BEFORE writing any visual file.
  foreach ($file in $stagedFiles) {
    $rel=$file.FullName.Substring($source.Length+1)
    $target=Join-Path $payload $rel
    $sourceSha=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    if (Test-Path -LiteralPath $target) {
      $existing=Get-Item -LiteralPath $target
      if ($existing.PSIsContainer -or
          ($existing.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "D02_PUBLISHED_FILE_COLLISION:$rel"
      }
      $prior=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
      if ($prior -cne $sourceSha -and !($rel -ceq 'Assets\index.html' -and
          $prior -ceq $originalIndexSha)) {
        throw "D02_PUBLISHED_UNAPPROVED_PREIMAGE:$rel"
      }
    }
  }
  $backupIndexPath=$null
  $publishedIndex=Join-Path $payload 'Assets/index.html'
  if (Test-Path -LiteralPath $publishedIndex -PathType Leaf) {
    $oldIndexSha=(Get-FileHash -LiteralPath $publishedIndex -Algorithm SHA256).Hash.ToLowerInvariant()
    $stageIndexSha=(Get-FileHash -LiteralPath $stagedIndex -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($oldIndexSha -cne $stageIndexSha) {
      $backupIndexPath=Join-Path $out 'D02_ORIGINAL_PUBLISHED_INDEX_BACKUP.html'
      if (Test-Path -LiteralPath $backupIndexPath) { throw 'D02_BACKUP_ALREADY_EXISTS_HOLD' }
      Copy-Item -LiteralPath $publishedIndex -Destination $backupIndexPath -ErrorAction Stop
      if ((Get-FileHash -LiteralPath $backupIndexPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $originalIndexSha) {
        throw 'D02_ORIGINAL_PUBLISHED_INDEX_BACKUP_SHA_HOLD'
      }
    }
  }
  foreach ($file in $stagedFiles) {
    $rel=$file.FullName.Substring($source.Length+1)
    $target=Join-Path $payload $rel
    $wanted=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    if (!(Test-Path -LiteralPath $target -PathType Leaf) -or
        (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -cne $wanted) {
      $folder=Split-Path -Parent $target
      if (!(Test-Path -LiteralPath $folder)) {
        New-Item -ItemType Directory -Path $folder -Force | Out-Null
      }
      Copy-Item -LiteralPath $file.FullName -Destination $target -Force -ErrorAction Stop
    }
    $actual=(Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -cne $wanted) { throw "D02_PUBLISHED_VISUAL_SHA_MISMATCH:$rel" }
    $visualPayloadRecords+=([ordered]@{path=$rel.Replace('\','/');sha256=$actual;bytes=(Get-Item -LiteralPath $target).Length})
  }
  $publishedHtml=Get-Content -LiteralPath $publishedIndex -Raw -Encoding UTF8
  if (([regex]::Matches($publishedHtml,[regex]::Escape('creative/wow200/runtime/home-scene.mjs'))).Count -ne 1) {
    throw 'D02_PUBLISHED_HOME_RUNTIME_IMPORT_HOLD'
  }
  foreach ($name in @('nox-cinema.mjs','nox-cinema.css')) {
    $wanted=Join-Path $source ('Assets/creative/wow200/proposals/NOX-CINEMA-FX/' + $name)
    $published=Join-Path $payload ('Assets/creative/wow200/proposals/NOX-CINEMA-FX/' + $name)
    if (!(Test-Path -LiteralPath $published -PathType Leaf) -or
        (Get-FileHash -LiteralPath $published -Algorithm SHA256).Hash -cne
        (Get-FileHash -LiteralPath $wanted -Algorithm SHA256).Hash) {
      throw 'D02_PUBLISHED_OWNER1_RENDERER_SHA_HOLD'
    }
  }
  $visualPayloadReceipt=Join-Path $out 'D02_VISUAL_PUBLISH_RECEIPT.json'
  $proof=[ordered]@{
    schema='NOX-E06-D02-VISUAL-PAYLOAD-V1';run_id=$RunId;source_only=$true;
    windows_qa_accepted=$false;original_index_sha256=$originalIndexSha;
    backup_original_index=$backupIndexPath;files=@($visualPayloadRecords);
    file_count=$visualPayloadRecords.Count;owner1_active_only=$true;
    previous_pr30_archived=$true;release_accepted=$false
  }
  [IO.File]::WriteAllText($visualPayloadReceipt,($proof | ConvertTo-Json -Depth 8),(New-Object System.Text.UTF8Encoding($false)))
}
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
# Include the existing program files in the conservative NSIS manifest.
$entries=@(Get-ChildItem -LiteralPath $payload -File -Recurse -Force | Sort-Object FullName | ForEach-Object {
  if (($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'NO_REPARSE_PAYLOAD' }
  $relative=$_.FullName.Substring($payload.Length).TrimStart('\')
  [ordered]@{path=$relative.Replace('\','/');bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
})
$manifest=[ordered]@{schema='NOX_P01_PAYLOAD_SHA256_V1';entrypoint='NOX.P01.Shell.exe';taskId='NOX-V16-E06-EXPRESS-ONEHOST';runId=$RunId;version='16.0.0';files=$entries}
$manifestPath=Join-Path $payload 'payload.sha256.json'
[IO.File]::WriteAllText($manifestPath,($manifest | ConvertTo-Json -Depth 7),(New-Object System.Text.UTF8Encoding($false)))
& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $installer 'Verify-Payload.ps1') -Root $payload -Manifest $manifestPath
if ($LASTEXITCODE -ne 0) { throw 'ORIGINAL_NSIS_PAYLOAD_SHA_GATE_HOLD' }
$setup=Join-Path $out 'NOX-HELION-V16-DIAGNOSTIC-SETUP.exe'
& $makensisPath /V2 "/DPAYLOAD_DIR=$payload" "/DVERIFY_SCRIPT=$(Join-Path $installer 'Verify-Payload.ps1')" "/DPREFLIGHT_SCRIPT=$(Join-Path $installer 'Preflight-InstallPath.ps1')" "/DREMOVE_SCRIPT=$(Join-Path $installer 'Remove-InstalledPayload.ps1')" "/DOUTPUT_SETUP=$setup" '/DAPP_VERSION=16.0.0' (Join-Path $installer 'NOX-HELION-Setup.nsi')
if ($LASTEXITCODE -ne 0 -or !(Test-Path -LiteralPath $setup -PathType Leaf)) { throw 'EXISTING_OWNER_NSIS_COMPILER_HOLD' }
$sha=(Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash.ToLowerInvariant()
$wpf=Join-Path $payload 'NOX.P01.Shell.exe'
$receipt=[ordered]@{
 schema='NOX-E06-ONEHOST-DIAGNOSTIC-NSIS-v1';run_id=$RunId;owner=6;
 wpf_exe_sha256=(Get-FileHash -LiteralPath $wpf -Algorithm SHA256).Hash.ToLowerInvariant();
 python_backend_sha256=$exeDigest;installer_sha256=$sha;installer_bytes=(Get-Item $setup).Length;
 payload_manifest_sha256=(Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash.ToLowerInvariant();
 original_D02_sha256=$assets;
 d02_visual_stage=$visualStage;
 d02_stage_receipt_sha256=if ($wantsCreative) {(Get-FileHash -LiteralPath $wowReceiptPath -Algorithm SHA256).Hash.ToLowerInvariant()} else {$null};
 d02_publish_receipt_sha256=if ($wantsCreative) {(Get-FileHash -LiteralPath $visualPayloadReceipt -Algorithm SHA256).Hash.ToLowerInvariant()} else {$null};
 d02_publish_visual_file_count=$visualPayloadRecords.Count;
 persona_media_staged=$wantsPersona;
 persona_stage_receipt_sha256=if ($wantsPersona) {(Get-FileHash -LiteralPath $personaReceiptPath -Algorithm SHA256).Hash.ToLowerInvariant()} else {$null};
 persona_windows_media_accepted=$false;
 status='WINDOWS_INSTALLER_CANDIDATE_NOT_E07_ACCEPTED';real_ollama_gpu_sip_tested=$false;
 one_visible_host=$true;native_bridge_scope='ORIGINAL_PYTHON_READ_ONLY_DIAGNOSE';
 installer_lifecycle_tested=$false;release_accepted=$false;owner_1_5_accepted=$false
}
$receiptPath=Join-Path $out 'ONEHOST_DIAGNOSTIC_RECEIPT.json'
[IO.File]::WriteAllText($receiptPath,($receipt | ConvertTo-Json -Depth 9),(New-Object System.Text.UTF8Encoding($false)))
Write-Host "E06_ONEHOST_NSIS_CANDIDATE_BUILT $sha"
