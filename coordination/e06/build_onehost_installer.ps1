# Owner E06: one WPF UI host with SHA-pinned original Python CLI backend.
# Existing owner P01 NSIS script, Verify-Payload and rollback/uninstall logic reused verbatim.
[CmdletBinding()]
param(
 [Parameter(Mandatory=$true)][string]$SourceRoot,
 [Parameter(Mandatory=$true)][string]$PythonExe,
 [Parameter(Mandatory=$true)][string]$OutputRoot,
 [Parameter(Mandatory=$true)][string]$RunId,
 [string]$PythonNativeSmokeReceipt='',
 [string]$CreativeSourceRoot='',
 [string]$WowSourceRoot='',
 [string]$PersonaBundlePath='',
 [string]$L01ApprovedInstallerUrl='',
 [int]$L01BootstrapVersion=0
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
$nativeEvidence='DIAGNOSE_ONLY_NOT_RUNTIME_PROOF'
$nativeLiveStatus='NOT_RUN'
$nativeProofSha=$null
if (-not [string]::IsNullOrWhiteSpace($PythonNativeSmokeReceipt)) {
  Assert-E06PlainPathAncestors -Candidate $PythonNativeSmokeReceipt -Scope 'NATIVE_PROOF'
  $proofPath=(Resolve-Path -LiteralPath $PythonNativeSmokeReceipt).Path
  $proof=Get-Content -LiteralPath $proofPath -Raw -Encoding UTF8 | ConvertFrom-Json
  $proofRepo=(Resolve-Path -LiteralPath (Join-Path $source '../../../..')).Path
  $proofGit=Get-Command git.exe -ErrorAction Stop
  $proofHead=(& $proofGit.Source -C $proofRepo rev-parse HEAD).Trim()
  if ($LASTEXITCODE -ne 0) { throw 'E06_PROOF_SOURCE_HEAD_REQUIRED' }
  $proofTree=(& $proofGit.Source -C $proofRepo rev-parse 'HEAD^{tree}').Trim()
  if ($LASTEXITCODE -ne 0) { throw 'E06_PROOF_SOURCE_TREE_REQUIRED' }
  foreach ($flag in @('run_id_matched','request_id_matched','original_729_unchanged',
      'release_accepted','installed_wpf_e07','process_restart_verified','isolated_test_data',
      'history_persistence_verified')) {
    if ($proof.$flag -isnot [bool]) { throw 'E06_NATIVE_PROOF_BOOLEAN_TYPE_REQUIRED' }
  }
  if (($proof.concurrent_native_executables_max -isnot [int] -and
       $proof.concurrent_native_executables_max -isnot [long]) -or
       $proof.concurrent_native_executables_max -ne 1) {
    throw 'E06_NATIVE_PROOF_PROCESS_COUNT_TYPE_REQUIRED'
  }
  if ($proof.schema -cne 'NOX_NATIVE_ONEHOST_SMOKE_V2' -or
      $proof.platform -cne 'win32' -or
      $proof.source_commit -cne $proofHead -or $proof.source_tree -cne $proofTree -or
      $proof.build_run_id -cne $RunId -or
      $proof.phase -cnotin @('BUILT_AND_NATIVE_STDIO_SMOKE_PASS','BUILT_AND_NATIVE_STDIO_SMOKE_HOLD') -or
      $proof.transport_status -cne 'PASS' -or $proof.offline_backbone_status -cne 'PASS' -or
      $proof.run_id_matched -ne $true -or $proof.request_id_matched -ne $true -or
      $proof.original_729_unchanged -ne $true -or $proof.release_accepted -ne $false -or
      $proof.installed_wpf_e07 -ne $false -or $proof.process_restart_verified -ne $true -or
      $proof.isolated_test_data -ne $true -or $proof.concurrent_native_executables_max -ne 1 -or
      $proof.source_original_archive_sha256 -cne 'ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a' -or
      $proof.exe_file -cne 'NOX_HELION_PRIVATE_CANDIDATE.exe' -or
      [string]$proof.exe_sha256 -cnotmatch '\A[0-9a-f]{64}\z' -or
      [string]$proof.build_receipt_sha256 -cnotmatch '\A[0-9a-f]{64}\z' -or
      [string]$proof.staged_original_app_sha256 -cnotmatch '\A[0-9a-f]{64}\z') {
    throw 'E06_NATIVE_STDIO_WINDOWS_RECEIPT_HOLD'
  }
  foreach ($route in @('chat.model','chat.history','chat.stop')) {
    if ($proof.routes.$route.status -cne 'PASS' -or $route -cnotin $proof.supported_routes_verified) {
      throw 'E06_NATIVE_OFFLINE_BACKBONE_INCOMPLETE'
    }
  }
  $nativeLiveStatus=[string]$proof.live_model_status
  if ($nativeLiveStatus -ceq 'PASS') {
    if ($proof.phase -cne 'BUILT_AND_NATIVE_STDIO_SMOKE_PASS' -or
        $proof.native_windows_exe_request_reply -cne 'PASS' -or
        $proof.routes.'helion.chat'.status -cne 'PASS' -or
        $proof.routes.'chat.stop'.live_cancel -cne 'PASS' -or
        $proof.history_persistence_verified -ne $true) {
      throw 'E06_NATIVE_LIVE_PROOF_INCONSISTENT'
    }
    $nativeEvidence='WINDOWS_EXE_NATIVE_BACKBONE_AND_LIVE_MODEL_PASS_NOT_E07'
  } elseif ($nativeLiveStatus -ceq 'HOLD' -and
            $proof.phase -ceq 'BUILT_AND_NATIVE_STDIO_SMOKE_HOLD' -and
            $proof.native_windows_exe_request_reply -ceq 'HOLD') {
    # A diagnostic installer can provision a real model later. It is never a release.
    $nativeEvidence='WINDOWS_EXE_OFFLINE_BACKBONE_PASS_LIVE_MODEL_HOLD'
  } else { throw 'E06_NATIVE_LIVE_STATUS_INVALID' }
  $exeDigest=[string]$proof.exe_sha256
  $nativeProofSha=(Get-FileHash -LiteralPath $proofPath -Algorithm SHA256).Hash.ToLowerInvariant()
}
if ((Get-FileHash -LiteralPath $original -Algorithm SHA256).Hash.ToLowerInvariant() -cne $exeDigest) { throw 'PYTHON_ORIGINAL_BINARY_SHA_HOLD' }
$project=Join-Path $source 'NOX.P01.Shell.csproj'
$installer=Join-Path $source 'Installer'
Assert-E06PlainPathAncestors -Candidate $project -Scope 'WPF_PROJECT'
Assert-E06PlainPathAncestors -Candidate (Join-Path $installer 'NOX-HELION-Setup.nsi') -Scope 'NSIS_OWNER'
if (!(Test-Path -LiteralPath $project -PathType Leaf)) { throw 'EXISTING_WPF_SOURCE_MISSING' }
if (!(Test-Path -LiteralPath (Join-Path $installer 'NOX-HELION-Setup.nsi') -PathType Leaf)) { throw 'ORIGINAL_NSIS_OWNER_SOURCE_MISSING' }

# E-F1 I0: correct only the disposable owner's WebView2 registry-view probe.
# Windows E06 41326203067 proved native HKLM Registry32 pv=156.0.4314.58
# while original Registry:: provider paths returned RUNTIME_MISSING.
# Preserve original runtime GUID, nonzero semantic version gate, installer
# ownership/reparse guards and fail-closed behavior. Source ZIP is untouched.
$webviewPreflight=Join-Path $installer 'Preflight-InstallPath.ps1'
Assert-E06PlainPathAncestors -Candidate $webviewPreflight -Scope 'P01_PREFLIGHT'
if (!(Test-Path -LiteralPath $webviewPreflight -PathType Leaf)) {
  throw 'E06_WEBVIEW2_ORIGINAL_PREFLIGHT_MISSING_HOLD'
}
$preflightOriginal=[IO.File]::ReadAllText($webviewPreflight)
$webviewStart='# Official Microsoft WebView2 runtime detection uses registry pv, not Edge browser presence.'
$webviewEnd="if (-not `$installed) { throw 'P01_WEBVIEW2_RUNTIME_MISSING: Install official Microsoft Evergreen WebView2 Runtime first; no silent download.' }"
$webviewBegin=$preflightOriginal.IndexOf($webviewStart,[StringComparison]::Ordinal)
$webviewFinish=$preflightOriginal.IndexOf($webviewEnd,[StringComparison]::Ordinal)
if ($webviewBegin -lt 0 -or $webviewFinish -le $webviewBegin -or
    $preflightOriginal.LastIndexOf($webviewStart,[StringComparison]::Ordinal) -ne $webviewBegin -or
    $preflightOriginal.LastIndexOf($webviewEnd,[StringComparison]::Ordinal) -ne $webviewFinish) {
  throw 'E06_WEBVIEW2_PREFLIGHT_ATOMIC_PREIMAGE_HOLD'
}
$webviewLegacy=$preflightOriginal.Substring($webviewBegin,$webviewFinish-$webviewBegin)
foreach ($mustContain in @('Registry::HKEY_CURRENT_USER','Registry::HKEY_LOCAL_MACHINE',
                          'Get-ItemProperty','[version]','pv')) {
  if (!$webviewLegacy.Contains($mustContain)) { throw 'E06_WEBVIEW2_PREFLIGHT_UNKNOWN_SOURCE_HOLD' }
}
$webviewReplacement=@'
# Official Microsoft WebView2 Evergreen Runtime: inspect the explicit 32/64-bit
# Windows registry views. Registry provider redirection is not relied upon.
# Microsoft Edge Stable alone is NOT an accepted runtime.
$clientPath='SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
$installed=$false
foreach ($hive in @([Microsoft.Win32.RegistryHive]::LocalMachine,
                    [Microsoft.Win32.RegistryHive]::CurrentUser)) {
  foreach ($view in @([Microsoft.Win32.RegistryView]::Registry32,
                      [Microsoft.Win32.RegistryView]::Registry64)) {
    $base=$null
    $key=$null
    try {
      $base=[Microsoft.Win32.RegistryKey]::OpenBaseKey($hive,$view)
      $key=$base.OpenSubKey($clientPath,$false)
      if ($null -ne $key) {
        $pv=$key.GetValue('pv',$null)
        if ($pv -is [string] -and $pv -cmatch '\A[0-9]+(?:\.[0-9]+){3}\z') {
          $runtimeVersion=[version]$pv
          if ($runtimeVersion.Major -gt 0) { $installed=$true }
        }
      }
    }
    finally {
      if ($null -ne $key) { $key.Dispose() }
      if ($null -ne $base) { $base.Dispose() }
    }
    if ($installed) { break }
  }
  if ($installed) { break }
}
'@
$eol=if ($preflightOriginal.Contains("`r`n")) { "`r`n" } else { "`n" }
$webviewReplacement=[regex]::Replace($webviewReplacement,'\r?\n',$eol)
$webviewPatched=$preflightOriginal.Substring(0,$webviewBegin)+
                $webviewReplacement+$eol+
                $preflightOriginal.Substring($webviewFinish)
if ($webviewPatched -ceq $preflightOriginal -or
    $webviewPatched -notmatch '\[Microsoft\.Win32\.RegistryView\]::Registry32' -or
    $webviewPatched -notmatch '\[Microsoft\.Win32\.RegistryView\]::Registry64' -or
    $webviewPatched -notmatch 'P01_WEBVIEW2_RUNTIME_MISSING') {
  throw 'E06_WEBVIEW2_PREFLIGHT_REPLACEMENT_GUARD_HOLD'
}
$preflightBefore=(Get-FileHash -LiteralPath $webviewPreflight -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::WriteAllText($webviewPreflight,$webviewPatched,(New-Object System.Text.UTF8Encoding($false)))
$preflightAfter=(Get-FileHash -LiteralPath $webviewPreflight -Algorithm SHA256).Hash.ToLowerInvariant()
if ($preflightBefore -ceq $preflightAfter) { throw 'E06_WEBVIEW2_PREFLIGHT_PATCH_NOT_APPLIED_HOLD' }
Write-Host "E06_WEBVIEW2_REGISTRY_VIEW_GUARDED_STAGE before_sha256=$preflightBefore after_sha256=$preflightAfter owner=I0"

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
$repoRoot=(Resolve-Path -LiteralPath (Join-Path $source '../../../..')).Path
$gitTool=Get-Command git.exe -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $gitTool) { throw 'E06_P02_GIT_BLOB_PROVENANCE_REQUIRED' }
# Preserve the exact original MainWindow SHA: native binding precedes Creative/WOW.
# Stage native WebView2/P02 activation only in the SHA-pinned original
# MainWindow copied to disposable R11; no changes to HOME/MENU/WORK or main.
$t06Stage=Join-Path $repoRoot 'coordination/e06/stage_native_p02.py'
$t06Addon=Join-Path $repoRoot 'coordination/e06/MainWindow.NativeP02.cs'
foreach ($part in @(@{p=$t06Stage;sha='594b4c5b825b244cec283d27d1fc0eea88b68abf'},@{p=$t06Addon;sha='1f9796364ac2bd0d3916ee8169de7ba7b5072c83'})) {
  Assert-E06PlainPathAncestors -Candidate $part.p -Scope 'T06_NATIVE'
  if (!(Test-Path -LiteralPath $part.p -PathType Leaf) -or
      (& $gitTool.Source hash-object -- $part.p).Trim().ToLowerInvariant() -cne $part.sha) {
    throw 'T06_ORIGINAL_MAINWINDOW_ADDON_SHA_HOLD'
  }
}
$stagePython=Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $stagePython) { throw 'T06_NATIVE_STAGE_PYTHON_REQUIRED' }
& $stagePython.Source $t06Stage $source $t06Addon $exeDigest
if ($LASTEXITCODE -ne 0) { throw 'T06_NATIVE_ORIGINAL_MAINWINDOW_STAGE_FAILED' }
# Original WPF uses the attested Python EXE over native framed stdio; E07 remains separately required.

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
  # The repository pins Git blobs in LF form. Windows checkout may convert
  # text to CRLF; verify the exact LF-normalized Git blob without weakening pins.
  function Get-E06CanonicalGitBlobSha([string] $Path) {
    $raw=[IO.File]::ReadAllBytes($Path)
    $utf8=New-Object System.Text.UTF8Encoding($false,$true)
    $body=$utf8.GetString($raw)
    if ($body.Replace("`r`n",'').Contains("`r")) {
      throw 'D02_STAGE_SCRIPT_BARE_CR_HOLD'
    }
    $normalized=$utf8.GetBytes($body.Replace("`r`n","`n"))
    $header=[Text.Encoding]::ASCII.GetBytes("blob $($normalized.Length)`0")
    $all=New-Object byte[] ($header.Length+$normalized.Length)
    [Array]::Copy($header,0,$all,0,$header.Length)
    [Array]::Copy($normalized,0,$all,$header.Length,$normalized.Length)
    $sha=[Security.Cryptography.SHA1]::HashData($all)
    return [Convert]::ToHexString($sha).ToLowerInvariant()
  }
  $creativeScriptBlob=Get-E06CanonicalGitBlobSha $creativeScript
  $wowScriptBlob=Get-E06CanonicalGitBlobSha $wowScript
  if ($creativeScriptBlob -cne '151caf9bdaabdcd24965fa2b030c5c700663cdf9' -or
      $wowScriptBlob -cne 'f97e19bbf674a3ab58ce9ac47be05d6945845b3c') {
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
  if ($wowReceipt.count -ne 78 -or $wowReceipt.p01_owner_source_staged -ne $true -or $wowReceipt.p01_owner_native_mount_activated -ne $false -or $wowReceipt.p01_owner_native_route_e2e -cne 'NOT_RUN' -or $wowReceipt.menu_v2_native_ui_staged -ne $true -or $wowReceipt.active_d02_engine -cne 'OWNER1_PR144_PINNED' -or
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
    # Windows checkout may expand original LF to CRLF. Compare the exact
    # staged bytes with the canonical immutable Git blob, not checkout bytes.
    $stageBlob=(& $gitTool.Source hash-object -- $active).Trim().ToLowerInvariant()
    if ($LASTEXITCODE -ne 0) { throw 'D02_ACTIVE_ENGINE_STAGE_GIT_BLOB_HOLD' }
    $sourceRevision='HEAD:proposals/NOX-CINEMA-FX/'+$name
    $sourceBlob=(& $gitTool.Source -C $repoRoot rev-parse $sourceRevision).Trim().ToLowerInvariant()
    if ($LASTEXITCODE -ne 0 -or $stageBlob -cne $sourceBlob) {
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
  # Existing P03 Micro-WOW screen: NO second app/renderer/queue. Strictly
  # copy exact Git-owned source bytes into the original disposable WPF Assets.
  # It is staged after the canonical D02 scripts to preserve their 69-file
  # locked receipt and the untouched HOME/MENU/WORK visual baseline.
  $microwowRoot=Join-Path (Resolve-Path -LiteralPath (Join-Path $source '../../../..')).Path 'Packages/P03/Source/P03.ModelCenter.Wow'
  $microwowTarget=Join-Path $source 'Assets/creative/modelcenter'
  $microwowFiles=@(
    @{relative='index.html';blob='e44efa7b5e2ffdfda6481c734f92c064fe1f458b'},
    @{relative='ui.css';blob='52757928eab65e474b9f500ab95b49adf3abe340'},
    @{relative='ui.js';blob='08d0e2d22ce2bd7b21d669804bf6a1577fbf7b17'},
    @{relative='THIRD_PARTY_LICENSES.txt';blob='4661952f5f4c9888c759ec94a3a28a31d26fc81f'},
    @{relative='icons/checkmark.svg';blob='e4ffbdc3d7f4f3e16a7612b7ab6bc145ad8874b6'},
    @{relative='icons/info.svg';blob='bd8e0cf27356e76acc68780ba6fd80cbfffbdf4f'},
    @{relative='icons/play.svg';blob='51b2a42674227622aa0b7af30a84a83b62faba49'},
    @{relative='icons/search.svg';blob='6c20f167dd93773c7a6e0b7aba9e054f4c07aedd'}
  )
  if (Test-Path -LiteralPath $microwowTarget) { throw 'P03_MICROWOW_STAGE_COLLISION' }
  foreach ($entry in $microwowFiles) {
    $microwowDonor=Join-Path $microwowRoot $entry.relative
    Assert-E06PlainPathAncestors -Candidate $microwowDonor -Scope 'P03_MICROWOW'
    if (!(Test-Path -LiteralPath $microwowDonor -PathType Leaf) -or
        (& $git.Source hash-object -- $microwowDonor).Trim().ToLowerInvariant() -cne $entry.blob) {
      throw 'P03_MICROWOW_EXACT_DONOR_SHA_HOLD'
    }
  }
  foreach ($entry in $microwowFiles) {
    $microwowDonor=Join-Path $microwowRoot $entry.relative
    $dest=Join-Path $microwowTarget $entry.relative
    New-Item -ItemType Directory -Path (Split-Path -Parent $dest) -Force | Out-Null
    Copy-Item -LiteralPath $microwowDonor -Destination $dest -ErrorAction Stop
    if ((& $git.Source hash-object -- $dest).Trim().ToLowerInvariant() -cne $entry.blob) {
      throw 'P03_MICROWOW_STAGE_READBACK_HOLD'
    }
  }
  $visualStage='D02_OWNER1_CANONICAL_STAGE_SHA_VERIFIED_SOURCE_ONLY'
}
if (Test-Path -LiteralPath $OutputRoot) { throw 'OUTPUT_ALREADY_EXISTS_NO_OVERWRITE' }
New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
Assert-E06PlainPathAncestors -Candidate $OutputRoot -Scope 'OUTPUT_POST_CREATE'
$out=(Resolve-Path $OutputRoot).Path
$payload=Join-Path $out 'payload'
# Stage the EXISTING P02 framed-pipe client plus the additive one-host WebView2
# adapter into the DISPOSABLE R11 source. Never alter approved original archives.
# This is compilable source only: live Python session and UI activation still
# require native Windows E2E, not a --diagnose receipt.
$p02StageSources=@(
  @{relative='Packages/P02/worker-chat/NativePythonPipe.cs';dest='Integration/NativePythonPipe.cs';blob='20c64c62c5b2c3f72c73ad106351d3af54cf0bd8'},
  @{relative='coordination/e06/OneHostP02WebView2Bridge.cs';dest='Integration/OneHostP02WebView2Bridge.cs';blob='2a655af31eadf19c179a40310f1b480a481af990'},
  @{relative='Packages/P03/Source/P03.ModelCenter/ModelArtifactReviewRegistry.cs';dest='Integration/P03/ModelArtifactReviewRegistry.cs';blob='ddc473ef4082c484a99c8d0681d0a3bb2e86e3bb'},
  @{relative='Packages/P03/Source/P03.ModelCenter/ModelCatalog.cs';dest='Integration/P03/ModelCatalog.cs';blob='12fc98f4b910b1760427ad73d077cdf382d525f3'},
  @{relative='Packages/P03/Source/P03.ModelCenter/ModelCenterNativeRoutes.cs';dest='Integration/P03/ModelCenterNativeRoutes.cs';blob='b63d20f9b5a7551d47d48cf96fa56569398602b4'},
  @{relative='Packages/P03/Source/P03.ModelCenter/ModelDownloadQueueStore.cs';dest='Integration/P03/ModelDownloadQueueStore.cs';blob='7c9a83d9b683090f12b058ac4c8907d388e4b6a5'},
  @{relative='Packages/P03/Source/P03.ModelCenter/ModelDownloadQueueWorker.cs';dest='Integration/P03/ModelDownloadQueueWorker.cs';blob='6dd5ceec428ec71a426d785304001a2d269a666f'},
  @{relative='Packages/P03/Source/P03.ModelCenter/ModelLifecycleEvents.cs';dest='Integration/P03/ModelLifecycleEvents.cs';blob='bfc2030334f78e78b35f510fc7f58ad19d1e75e4'},
  @{relative='Packages/P03/Source/P03.ModelCenter/ModelLocalAttestation.cs';dest='Integration/P03/ModelLocalAttestation.cs';blob='e55bd2ec0e13a50ef026ae4055fe71b5f7a4e4ed'},
  @{relative='Packages/P03/Source/P03.ModelCenter/ModelQuickActions.cs';dest='Integration/P03/ModelQuickActions.cs';blob='66d6f05c8f2deea7fab110f4c024d762d71af390'},
  @{relative='Packages/P03/Source/P03.ModelCenter/ModelSafetensorsImport.cs';dest='Integration/P03/ModelSafetensorsImport.cs';blob='6364e3ae1a525b6ec836be98eea7bcd5f268afc0'},
  @{relative='Packages/P03/Source/P03.ModelCenter/ModelTagReviewLeads.cs';dest='Integration/P03/ModelTagReviewLeads.cs';blob='439aa3cf82e20a77d12755c9ac4a7c5ef04c2f79'},
  @{relative='Packages/P03/Source/P03.ModelCenter/ModelWowBridgeContract.cs';dest='Integration/P03/ModelWowBridgeContract.cs';blob='0c8fa6b409e64ac5a6636a4ae2f46b36f79f1ced'},
  @{relative='Packages/P03/Source/P03.ModelCenter/OllamaLoopbackHttpClientFactory.cs';dest='Integration/P03/OllamaLoopbackHttpClientFactory.cs';blob='9785e258c563027567e83b76d22ee66bf350f064'},
  @{relative='Packages/P03/Source/P03.ModelCenter/OllamaModelAdapter.cs';dest='Integration/P03/OllamaModelAdapter.cs';blob='ed4d55e053fd88f6e69911889981b566d3701661'},
  @{relative='Packages/P03/Source/P03.ModelCenter/WindowsHardwareFacts.cs';dest='Integration/P03/WindowsHardwareFacts.cs';blob='401f2cf9b318575542fce77db6571dd3ce2ee8f4'}
)
# Validate every donor BEFORE copying any source into the staged project.
foreach ($entry in $p02StageSources) {
  $origin=Join-Path $repoRoot $entry.relative
  $target=Join-Path $source $entry.dest
  Assert-E06PlainPathAncestors -Candidate $origin -Scope 'P02_SOURCE'
  Assert-E06PlainPathAncestors -Candidate $target -Scope 'P02_STAGE'
  if (!(Test-Path -LiteralPath $origin -PathType Leaf) -or
      (Test-Path -LiteralPath $target)) { throw 'E06_P02_SOURCE_MISSING_OR_STAGE_COLLISION' }
  $actual=(& $gitTool.Source hash-object -- $origin).Trim().ToLowerInvariant()
  if ($LASTEXITCODE -ne 0 -or $actual -cne $entry.blob) {
    throw 'E06_P02_OWNER_BLOB_MISMATCH'
  }
}
foreach ($entry in $p02StageSources) {
  $origin=Join-Path $repoRoot $entry.relative
  $target=Join-Path $source $entry.dest
  New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
  Copy-Item -LiteralPath $origin -Destination $target -ErrorAction Stop
  $post=(& $gitTool.Source hash-object -- $target).Trim().ToLowerInvariant()
  if ($LASTEXITCODE -ne 0 -or $post -cne $entry.blob) {
    throw 'E06_P02_DISPOSABLE_STAGE_SHA_MISMATCH'
  }
}
# T06: fix 17 malformed original P05 C# HTML raw-string fragments in the
# disposable SHA-verified R11 stage; exact reversible transformation only.
$p05Repair=Join-Path $repoRoot 'coordination/e06/stage_p05_html_verbatim.py'
Assert-E06PlainPathAncestors -Candidate $p05Repair -Scope 'P05_DISPOSABLE_REPAIR'
if (!(Test-Path -LiteralPath $p05Repair -PathType Leaf) -or
    (& $gitTool.Source hash-object -- $p05Repair).Trim().ToLowerInvariant() -cne '3c250033f62ea6cb1c4e1607048b9bbad6c971d9') {
  throw 'E06_P05_REPAIR_PIN_HOLD'
}
& $stagePython.Source $p05Repair $source
if ($LASTEXITCODE -ne 0) { throw 'E06_P05_EXACT_HTML_REPAIR_HOLD' }
# T06: only exact original-owner duplicate declarations & missing using
# repairs, in disposable R11. No P03 functionality, approved art or history lost.
$wpfCompat=Join-Path $repoRoot 'coordination/e06/stage_wpf_compat_no_loss.py'
Assert-E06PlainPathAncestors -Candidate $wpfCompat -Scope 'WPF_COMPAT'
if (!(Test-Path -LiteralPath $wpfCompat -PathType Leaf) -or
    (& $gitTool.Source hash-object -- $wpfCompat).Trim().ToLowerInvariant() -cne 'fc206205ec46e52d8d65eab33490193a27d1529a') {
  throw 'E06_WPF_COMPAT_SOURCE_PIN_HOLD'
}
& $stagePython.Source $wpfCompat $source
if ($LASTEXITCODE -ne 0) { throw 'E06_WPF_EXACT_COMPAT_STAGE_HOLD' }
# R51 reuses native BCL and the original P03/EventV3 owners: 8 guarded repairs
# in disposable R11; original ZIP/HOME/MENU/WORK remain byte-identical.
$finalWpfCompat=Join-Path $repoRoot 'coordination/e06/stage_wpf_final8_no_loss.py'
Assert-E06PlainPathAncestors -Candidate $finalWpfCompat -Scope 'WPF_R51'
if (!(Test-Path -LiteralPath $finalWpfCompat -PathType Leaf) -or
    (& $gitTool.Source hash-object -- $finalWpfCompat).Trim().ToLowerInvariant() -cne '98bf0c54761f033cba30a9bd522afa12b5d7f2d9') {
  throw 'E06_R51_WPF_OWNER_SOURCE_SHA_HOLD'
}
& $stagePython.Source $finalWpfCompat $source
if ($LASTEXITCODE -ne 0) { throw 'E06_R51_WPF_OWNER_COMPAT_STAGE_HOLD' }
# The native ModelCenter reads an owner-pinned registry, never browser-supplied
# rights or digests. Empty reviewed items stay REVIEW_REQUIRED without downloads.
$p03Registry=Join-Path $repoRoot 'contracts/p03_reviewed_artifacts.json'
Assert-E06PlainPathAncestors -Candidate $p03Registry -Scope 'P03_REVIEW_REGISTRY'
$p03RegistrySha='3b47af8b85aefd88408dd5cc63ad9615da87427d4d0cb2b56b0f5a4246ffbd60'
if (!(Test-Path -LiteralPath $p03Registry -PathType Leaf)) {
  throw 'P03_REVIEW_REGISTRY_SOURCE_SHA_HOLD'
}
# Git LF sources may be checked out with CRLF on Windows. Admit only the
# exact pinned UTF-8 LF bytes and publish those bytes, never a normalized
# but unverified different model-rights manifest.
$registryUtf8=[System.Text.UTF8Encoding]::new($false,$true)
$registryText=$registryUtf8.GetString([IO.File]::ReadAllBytes($p03Registry))
$registryCanonicalText=$registryText.Replace("`r`n","`n")
if ($registryCanonicalText.Contains("`r") -or
    $registryCanonicalText.Contains([char]0xFEFF)) {
  throw 'P03_REVIEW_REGISTRY_UNSAFE_ENCODING'
}
$registryCanonicalBytes=$registryUtf8.GetBytes($registryCanonicalText)
$registryCanonicalSha=[Convert]::ToHexString(
    [Security.Cryptography.SHA256]::HashData($registryCanonicalBytes)).ToLowerInvariant()
if ($registryCanonicalSha -cne $p03RegistrySha) {
  throw 'P03_REVIEW_REGISTRY_SOURCE_SHA_HOLD'
}
& dotnet publish $project -c Release -r win-x64 --self-contained true -p:PublishSingleFile=false -p:PublishTrimmed=false -o $payload --nologo --verbosity minimal
if ($LASTEXITCODE -ne 0) { throw 'ONEHOST_WPF_SELFCONTAINED_PUBLISH_HOLD' }
if (!(Test-Path -LiteralPath (Join-Path $payload 'NOX.P01.Shell.exe'))) { throw 'WPF_ENTRYPOINT_MISSING' }
$p03PublishedRegistry=Join-Path $payload 'contracts/p03_reviewed_artifacts.json'
Assert-E06PlainPathAncestors -Candidate $p03PublishedRegistry -Scope 'P03_REVIEW_PAYLOAD'
if (Test-Path -LiteralPath $p03PublishedRegistry) { throw 'P03_REVIEW_PAYLOAD_COLLISION' }
New-Item -ItemType Directory -Path (Split-Path -Parent $p03PublishedRegistry) -Force | Out-Null
[IO.File]::WriteAllBytes($p03PublishedRegistry,$registryCanonicalBytes)
if ((Get-FileHash -LiteralPath $p03PublishedRegistry -Algorithm SHA256).Hash.ToLowerInvariant() -cne $p03RegistrySha) {
  throw 'P03_REVIEW_REGISTRY_PAYLOAD_SHA_HOLD'
}
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
 one_visible_host=$true;native_bridge_scope=$nativeEvidence;
 native_live_model_status=$nativeLiveStatus;native_smoke_receipt_sha256=$nativeProofSha;
 installer_lifecycle_tested=$false;release_accepted=$false;owner_1_5_accepted=$false
}
$receiptPath=Join-Path $out 'ONEHOST_DIAGNOSTIC_RECEIPT.json'
[IO.File]::WriteAllText($receiptPath,($receipt | ConvertTo-Json -Depth 9),(New-Object System.Text.UTF8Encoding($false)))
# L02 additive bridge to the existing L01 downloader. No new installer or trust override.
# Owner-supplied HTTPS release asset URL is optional; absent URL means no manifest.
# Existing E06 diagnostic receipt stays HOLD until independent installed acceptance.
if (-not [string]::IsNullOrWhiteSpace($L01ApprovedInstallerUrl)) {
  if ($L01BootstrapVersion -le 0 -or $L01BootstrapVersion -gt 2147483647) {
    throw 'L01_BOOTSTRAP_VERSION_MUST_BE_OWNER_APPROVED'
  }
  $bridge=Join-Path $PSScriptRoot 'l01_manifest_bridge.py'
  if (!(Test-Path -LiteralPath $bridge -PathType Leaf)) { throw 'L02_PINNED_BRIDGE_SOURCE_MISSING' }
  $python=Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -First 1
  if (!$python) { throw 'L02_PYTHON_TOOLCHAIN_UNAVAILABLE' }
  $l01Candidate=Join-Path $out 'NOX-HELION-RELEASE.txt'
  & $python.Source $bridge --setup $setup --receipt $receiptPath --approved-url $L01ApprovedInstallerUrl --version $L01BootstrapVersion --out $l01Candidate
  if ($LASTEXITCODE -ne 0 -or !(Test-Path -LiteralPath $l01Candidate -PathType Leaf)) {
    throw 'L02_L01_MANIFEST_SOURCE_GATE_HOLD'
  }
  Write-Host 'L02_L01_MANIFEST_CANDIDATE_CREATED_NOT_RELEASE_APPROVED'
}
Write-Host "E06_ONEHOST_NSIS_CANDIDATE_BUILT $sha"
