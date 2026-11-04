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
 [switch]$IncludeMega814,
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
# Freeze actual canonical checkout before compiling existing OneHost/NSIS.
$e06RepoRoot=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
$e06SourceHead=((& git -C $e06RepoRoot rev-parse HEAD) | Out-String).Trim().ToLowerInvariant()
if ($LASTEXITCODE -ne 0 -or $e06SourceHead -cnotmatch '\A[0-9a-f]{40}\z') { throw 'E06_SOURCE_HEAD_UNAVAILABLE' }
# I0 frozen original source: HEAD alone does not attest staged/unstaged tracked bytes.
# Refuse a dirty checkout before invoking the original WPF/Python/NSIS stages.
& git -C $e06RepoRoot diff --quiet --exit-code HEAD --
if ($LASTEXITCODE -ne 0) { throw 'E06_TRACKED_CHECKOUT_DIRTY_BEFORE_BUILD' }
$exeDigest='4e488372cf3f6410d268a7ef72b3e4b359a7a3e6642c7a16ac2e6f7eb06fc5f3'
$nativeEvidence='DIAGNOSE_ONLY_NOT_RUNTIME_PROOF'
$nativeLiveStatus='NOT_RUN'
$nativeProofSha=$null
if (-not [string]::IsNullOrWhiteSpace($PythonNativeSmokeReceipt)) {
  Assert-E06PlainPathAncestors -Candidate $PythonNativeSmokeReceipt -Scope 'NATIVE_PROOF'
  $proofPath=(Resolve-Path -LiteralPath $PythonNativeSmokeReceipt).Path
  # Parse the EXACT native evidence bytes through a pinned, bounded strict JSON
  # admission gate. Windows PowerShell ConvertFrom-Json is last-wins on
  # duplicate JSON keys; after canonicalization it cannot reinterpret origin,
  # status, approval or STOP receipts. No new native grant is generated.
  $nativeVerifier=Join-Path $PSScriptRoot 'verify_native_receipt_json.py'
  Assert-E06PlainPathAncestors -Candidate $nativeVerifier -Scope 'NATIVE_JSON_VERIFIER'
  if (!(Test-Path -LiteralPath $nativeVerifier -PathType Leaf)) {
    throw 'E06_NATIVE_RECEIPT_STRICT_JSON_HOLD'
  }
  $expectedNativeVerifierBlob='b14809eb5479d612b78282fd6eb210ad55d72cce'
  $nativeVerifierBlob=((& git -C $e06RepoRoot hash-object -- $nativeVerifier) | Out-String).Trim().ToLowerInvariant()
  if ($LASTEXITCODE -ne 0 -or $nativeVerifierBlob -cne $expectedNativeVerifierBlob) {
    throw 'E06_NATIVE_RECEIPT_VERIFIER_PIN_HOLD'
  }
  $nativeStrictPython=Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -First 1
  if (!$nativeStrictPython) { throw 'E06_NATIVE_RECEIPT_PYTHON_REQUIRED' }
  $strictOutput=@(& $nativeStrictPython.Source $nativeVerifier $proofPath 2>$null)
  if ($LASTEXITCODE -ne 0 -or $strictOutput.Count -ne 1) {
    throw 'E06_NATIVE_RECEIPT_STRICT_JSON_HOLD'
  }
  $strictEntry=[string]$strictOutput[0]
  if ($strictEntry.Length -lt 67 -or $strictEntry.IndexOf([char]9) -ne 64 -or
      $strictEntry.Substring(0,64) -cnotmatch '\A[0-9a-f]{64}\z') {
    throw 'E06_NATIVE_RECEIPT_STRICT_JSON_HOLD'
  }
  $nativeProofSha=$strictEntry.Substring(0,64)
  $proof=$strictEntry.Substring(65) | ConvertFrom-Json
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
  # SHA-256 above is bound to the single strictly decoded receipt byte stream.
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
# Another approved stage may already have applied this exact 32/64-bit registry
# gate in the disposable R11. Accept byte-identical canonical content only.
$canonicalWebviewBlock=$webviewReplacement+$eol
$alreadyCanonical=($webviewLegacy -ceq $canonicalWebviewBlock)
if (!$alreadyCanonical) {
  # The immutable C07 original (ZIP SHA256
  # 90076eba83a213ba2b410632ced3288d41a6691ab63f81ad0520aa3cbbbfcb52)
  # has a legacy pv nonzero check without the later [version] cast.
  # Accept that known historical preimage only by exact SHA-256, then replace
  # with the approved strict Registry32/Registry64 + [version] gate below.
  $legacySha=[Convert]::ToHexString(
    [Security.Cryptography.SHA256]::HashData(
      [Text.Encoding]::UTF8.GetBytes(($webviewLegacy -replace "`r`n","`n"))
    )).ToLowerInvariant()
  $knownC07Legacy=($legacySha -ceq 'a61e2e7adcbf836109249829f4d103e0d991873c0088483b0b3550216a4b4c8e')
  if (!$knownC07Legacy) {
    foreach ($mustContain in @('Registry::HKEY_CURRENT_USER','Registry::HKEY_LOCAL_MACHINE',
                              'Get-ItemProperty','[version]','pv')) {
      if (!$webviewLegacy.Contains($mustContain)) {
        throw 'E06_WEBVIEW2_PREFLIGHT_UNKNOWN_SOURCE_HOLD'
      }
    }
  }
  $webviewPatched=$preflightOriginal.Substring(0,$webviewBegin)+
                  $canonicalWebviewBlock+
                  $preflightOriginal.Substring($webviewFinish)
} else {
  $webviewPatched=$preflightOriginal
}
if ((!$alreadyCanonical -and $webviewPatched -ceq $preflightOriginal) -or
    $webviewPatched -notmatch '\[Microsoft\.Win32\.RegistryView\]::Registry32' -or
    $webviewPatched -notmatch '\[Microsoft\.Win32\.RegistryView\]::Registry64' -or
    $webviewPatched -notmatch 'P01_WEBVIEW2_RUNTIME_MISSING') {
  throw 'E06_WEBVIEW2_PREFLIGHT_REPLACEMENT_GUARD_HOLD'
}
$preflightBefore=(Get-FileHash -LiteralPath $webviewPreflight -Algorithm SHA256).Hash.ToLowerInvariant()
if ($alreadyCanonical) {
  # No rewrite of an already approved byte-identical preflight.
  $preflightAfter=$preflightBefore
  Write-Host "E06_WEBVIEW2_PREFLIGHT_ALREADY_STAGED_EXACT_REGISTRY32_64 sha256=$preflightBefore"
} else {
  [IO.File]::WriteAllText($webviewPreflight,$webviewPatched,(New-Object System.Text.UTF8Encoding($false)))
  $preflightAfter=(Get-FileHash -LiteralPath $webviewPreflight -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($preflightBefore -ceq $preflightAfter) { throw 'E06_WEBVIEW2_PREFLIGHT_PATCH_NOT_APPLIED_HOLD' }
  Write-Host "E06_WEBVIEW2_REGISTRY_VIEW_GUARDED_STAGE before_sha256=$preflightBefore after_sha256=$preflightAfter owner=I0"
}

# The original diagnostic builder keeps its existing behavior unless BOTH visual
# sources are explicitly supplied. Never silently use an old D02 donor.
if ($IncludeMega814 -and [string]::IsNullOrWhiteSpace($CreativeSourceRoot)) { throw 'MEGAB_REQUIRES_CANONICAL_D02_WOW_STAGING' }
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
foreach ($part in @(@{p=$t06Stage;sha='a48469a896ee03ed4fe680aab8748597abaa65fb'},@{p=$t06Addon;sha='6252757c9bc154ee6e4831a18512ca8f315dc548'})) {
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
    # Windows PowerShell 5.1/.NET Framework lacks static SHA1.HashData and Convert.ToHexString.
    # Preserve exact Git blob SHA1 over header + LF-normalized bytes; release on all paths.
    $gitBlobHasher=[Security.Cryptography.SHA1]::Create()
    try {
      $sha=$gitBlobHasher.ComputeHash($all)
    } finally {
      $gitBlobHasher.Dispose()
    }
    return ([BitConverter]::ToString($sha).Replace('-','')).ToLowerInvariant()
  }
  $creativeScriptBlob=Get-E06CanonicalGitBlobSha $creativeScript
  $wowScriptBlob=Get-E06CanonicalGitBlobSha $wowScript
  if ($creativeScriptBlob -cne '151caf9bdaabdcd24965fa2b030c5c700663cdf9' -or
      $wowScriptBlob -cne '30d0b3f57cd408d3faaa390961739dda7a7bc7ee') {
    throw 'D02_PINNED_STAGE_SCRIPT_SHA_HOLD'
  }
  if (Test-Path -LiteralPath (Join-Path $source 'Assets/creative')) {
    throw 'D02_CREATIVE_STAGE_ALREADY_PRESENT'
  }
  # Existing ORIGINAL five-primary R11 publisher must run on the disposable
  # FULL D02 Home BEFORE Creative/WOW. Old full D02 physical UIA found 0/5.
  # No new frontend/backend, no scripted fake actions, no ACL/consent changes.
  $primaryOwner=Join-Path $repoRoot 'coordination/express/stage_original_five_primary.py'
  $primaryStage=Join-Path $repoRoot 'coordination/express/publish_original_d02_primary_u12.py'
  foreach ($pinned in @(
    @{path=$primaryOwner;sha='ada88a8f36f98f6a91469b90a0b69e1cfc867ce7'},
    @{path=$primaryStage;sha='931ecac66e89fcde15c55c1e26a6b2e137c3b6ea'})) {
    Assert-E06PlainPathAncestors -Candidate $pinned.path -Scope 'D02_PRIMARY_SCRIPT'
    if (!(Test-Path -LiteralPath $pinned.path -PathType Leaf) -or
        (Get-E06CanonicalGitBlobSha $pinned.path) -cne $pinned.sha) {
      throw 'D02_PRIMARY_REVIEWED_SOURCE_PIN_HOLD'
    }
  }
  $primaryHome=Join-Path $source 'Assets/index.html'
  Assert-E06PlainPathAncestors -Candidate $primaryHome -Scope 'D02_PRIMARY_HOME'
  if (!(Test-Path -LiteralPath $primaryHome -PathType Leaf) -or
      (Get-FileHash -LiteralPath $primaryHome -Algorithm SHA256).Hash.ToLowerInvariant() -cne
      'b57d58bb001c9826feb3bf7ff19510d047c7ec2926ee8b703538dfca886a960b') {
    throw 'D02_PRIMARY_ORIGINAL_HOME_SOURCELOCK_HOLD'
  }
  $primaryReceipt=Join-Path (Split-Path -Parent $source) 'EXPRESS_PRIMARY_STAGE_RECEIPT.json'
  Assert-E06PlainPathAncestors -Candidate $primaryReceipt -Scope 'D02_PRIMARY_RECEIPT'
  if (Test-Path -LiteralPath $primaryReceipt) { throw 'D02_PRIMARY_RECEIPT_COLLISION_HOLD' }
  & $py.Source -B $primaryStage $source $primaryReceipt
  if ($LASTEXITCODE -ne 0) { throw 'D02_PRIMARY_CANONICAL_ACTION_STAGE_HOLD' }
  $primaryProof=Get-Content -LiteralPath $primaryReceipt -Raw -Encoding UTF8 | ConvertFrom-Json
  if ($primaryProof.source_sha256 -cne
      'b57d58bb001c9826feb3bf7ff19510d047c7ec2926ee8b703538dfca886a960b' -or
      $primaryProof.status -cne 'STAGED_SOURCE_ONLY_NOT_UIA' -or
      $primaryProof.installed_ui_automation -cne 'NOT_RUN' -or
      $primaryProof.release_accepted -ne $false -or
      $primaryProof.original_source_archive_unchanged -ne $true -or
      (Get-FileHash -LiteralPath $primaryHome -Algorithm SHA256).Hash.ToLowerInvariant() -cne
      $primaryProof.published_sha256) {
    throw 'D02_PRIMARY_STAGED_SOURCE_PROOF_HOLD'
  }
  & $py.Source $creativeScript $source $creative
  if ($LASTEXITCODE -ne 0) { throw 'D02_CREATIVE_STAGE_FAILED' }
  & $py.Source $wowScript $source $wow
  if ($LASTEXITCODE -ne 0) { throw 'D02_WOW_STAGE_FAILED' }
  $wowReceiptPath=Join-Path (Split-Path -Parent $source) 'WOW200_STAGE_RECEIPT.json'
  if (!(Test-Path -LiteralPath $wowReceiptPath -PathType Leaf)) { throw 'D02_WOW_STAGE_RECEIPT_MISSING' }
  $wowReceipt=Get-Content -LiteralPath $wowReceiptPath -Raw -Encoding UTF8 | ConvertFrom-Json
  # 56 pinned donors + 2 active canonical D02 copies + 8 MENU files +
  # 9 P01 owner files + 8 reviewed runtime files + catalog + 2 HTML = 86.
  # Reject omitted or duplicated staged paths BEFORE WPF/NSIS publish.
  $wowPaths=@($wowReceipt.files | ForEach-Object { [string]$_.path })
  if ($wowReceipt.count -ne 86 -or $wowPaths.Count -ne 86 -or
      @($wowPaths | Sort-Object -Unique).Count -ne 86 -or
      @($wowPaths | Where-Object { [string]::IsNullOrWhiteSpace($_) }).Count -ne 0) {
    throw 'D02_WOW_STAGE_RECEIPT_FILESET_HOLD'
  }
  if ($wowReceipt.original_chrome_compact_git_blob -cne '8e3cffe7cb91564ae5817e55cb35e5fbb0feeb50' -or
      $wowReceipt.original_chrome_source_staged -ne $true -or
      $wowReceipt.original_chrome_visual_e07 -cne 'HOLD' -or
      $wowReceipt.count -ne 86 -or $wowReceipt.p01_owner_source_staged -ne $true -or $wowReceipt.p01_owner_native_mount_activated -ne $false -or $wowReceipt.p01_owner_native_route_e2e -cne 'NOT_RUN' -or $wowReceipt.menu_v2_native_ui_staged -ne $true -or $wowReceipt.active_d02_engine -cne 'OWNER1_PR144_PINNED' -or
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
  if ($IncludeMega814) {
    # Stage the existing approved planetary MENU10 ONLY in the disposable R11.
    # No new host, no replacement of the eight original CoreID routes.
    $menuRoot=Join-Path $repoRoot 'coordination/mega814'
    $menuStage=Join-Path $menuRoot 'stage_original_r11.py'
    $menuGate=Join-Path $menuRoot 'qa_source_gate.py'
    $menuPublisher=Join-Path $menuRoot 'publish_onehost_payload.py'
    foreach ($candidate in @(
      @{Path=$menuStage;Blob='0b34802f451636e32c61ad40d8d30bf279b515e0'},
      @{Path=$menuGate;Blob='d5b1ee5f3dbf622c21acc16594f980ebc04ceb1d'},
      @{Path=$menuPublisher;Blob='6e2a943ab3f0a69d3dea641fdd78748922675dd8'}
    )) {
      Assert-E06PlainPathAncestors -Candidate $candidate.Path -Scope 'MENU10_SOURCE'
      if (!(Test-Path -LiteralPath $candidate.Path -PathType Leaf) -or
          (Get-E06CanonicalGitBlobSha $candidate.Path) -cne $candidate.Blob) {
        throw 'MEGAB_SOURCE_SCRIPT_PIN_HOLD'
      }
    }
    & $py.Source $menuGate
    if ($LASTEXITCODE -ne 0) { throw 'MEGAB_APPROVED_MENU10_SOURCE_QA_HOLD' }
    & $py.Source $menuStage --r11 $source
    if ($LASTEXITCODE -ne 0) { throw 'MEGAB_OWNER_R11_MENU10_STAGE_HOLD' }
    Write-Host 'E06_APPROVED_MENU10_10_WORLDS_STAGED_NOT_E07'
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
    @{relative='index.html';blob='d4b80dbdc7669272da9391bb17db51bfad68de7e'},
    @{relative='ui.css';blob='dfac6e254f205d121330a71cad206e2158cf2de2'},
    @{relative='ui.js';blob='f464ea25670958661de127a638f1cf0ffa48f5dd'},
    @{relative='vendor/uPlot.iife.min.js';blob='6749c4f02499c6999245f406f4bd208985f89aee'},
    @{relative='vendor/uPlot.min.css';blob='976000608e7ee21ef0c700b08ad6f90834b40055'},
    @{relative='vendor/uPlot.LICENSE.txt';blob='cde4b3f8352d147d5e626fea36358797c4fc06f2'},
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
  @{relative='Packages/P02/worker-chat/NativePythonPipe.cs';dest='Integration/NativePythonPipe.cs';blob='e8e4f95106f4d40c29c68d81378c7938e6a7c0f5'},
  @{relative='coordination/e06/OneHostP02WebView2Bridge.cs';dest='Integration/OneHostP02WebView2Bridge.cs';blob='31c03910102687942df7fdbb363182f9cfb2cd09'},
  @{relative='Packages/P02/worker-chat/SpaceBrowserBoundary.cs';dest='Integration/SpaceBrowserBoundary.cs';blob='4d70c5de450837d07304d91b4fa4c0e049a2be52'},
  @{relative='coordination/e06/NoXAutostart.cs';dest='Integration/NoXAutostart.cs';blob='5ae879ce474e6279cccd57fb596705959dbb3c9e'},
  @{relative='Packages/P03/Source/P03.ModelCenter/ModelArtifactReviewRegistry.cs';dest='Integration/P03/ModelArtifactReviewRegistry.cs';blob='06795f2e4c6688e4e2f12897182dae3f571e17d6'},
  @{relative='Packages/P03/Source/P03.ModelCenter/ModelCatalog.cs';dest='Integration/P03/ModelCatalog.cs';blob='e565efa8ad53ed811f0d77158eec55b1f078ddb8'},
  @{relative='Packages/P03/Source/P03.ModelCenter/ModelCenterNativeRoutes.cs';dest='Integration/P03/ModelCenterNativeRoutes.cs';blob='07b137096122e1df9869d75386bf657d154214a1'},
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
# SHA-256 of exact approved LF UTF-8 registry; PS5.1-safe, no digest bypass.
$registryHasher=[Security.Cryptography.SHA256]::Create()
try {
  $registryCanonicalSha=([BitConverter]::ToString(
      $registryHasher.ComputeHash($registryCanonicalBytes)).Replace('-','')).ToLowerInvariant()
} finally {
  $registryHasher.Dispose()
}
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
  # Attest the exact published payload, not merely a staged or decorative UI.
  # Real Windows WebView2 UIA InvokePattern is still E07 HOLD until executed.
  if (!$publishedHtml.Contains('id="nox-express-primary"') -or
      ([regex]::Matches($publishedHtml,'data-nox-primary="(?:CHAT|INSTALL|MODELS|LEARN|SETTINGS)"')).Count -ne 5 -or
      !$publishedHtml.Contains('nox-express-primary-bind')) {
    throw 'D02_PUBLISHED_FIVE_ORIGINAL_PRIMARY_ACTIONS_MISSING'
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
    previous_pr30_archived=$true;express_original_five_primary_source_only=$true;
    express_primary_stage_receipt_sha256=(Get-FileHash -LiteralPath $primaryReceipt -Algorithm SHA256).Hash.ToLowerInvariant();
    express_primary_physical_uia='NOT_RUN';release_accepted=$false
  }
  [IO.File]::WriteAllText($visualPayloadReceipt,($proof | ConvertTo-Json -Depth 8),(New-Object System.Text.UTF8Encoding($false)))
}
if ($IncludeMega814) {
  # Verify the actual WPF published Content path, including 10 asteroid media,
  # 193-entry catalog, native relative import and exact owner receipt.
  & $stagePython.Source $menuPublisher --r11 $source --payload $payload
  if ($LASTEXITCODE -ne 0) { throw 'MEGAB_APPROVED_MENU10_PUBLISHED_PAYLOAD_HOLD' }
  $menu10Published=Join-Path $payload 'Assets/mega814/menu10.png'
  if (!(Test-Path -LiteralPath $menu10Published -PathType Leaf) -or
      (Get-FileHash -LiteralPath $menu10Published -Algorithm SHA256).Hash.ToLowerInvariant() -cne
      '1cdc1d9d6f17033bf4a1c6a8ec1b8f5816ab35ddd5ed6d682eb8a190e1943dca') {
    throw 'MEGAB_OWNER_MENU10_CANONICAL_IMAGE_SHA_HOLD'
  }
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
# I0 P01: inspect the entire published directory graph BEFORE enumerating files.
# File-only inventories may miss a directory junction that NSIS File /r could
# traverse. Walk one level at a time; reject reparse nodes BEFORE descent.
Assert-E06PlainPathAncestors -Candidate $payload -Scope 'NSIS_PAYLOAD'
$payloadRootInfo=Get-Item -LiteralPath $payload -Force -ErrorAction Stop
if (!$payloadRootInfo.PSIsContainer -or
    ($payloadRootInfo.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
  throw 'E06_NSIS_PAYLOAD_ROOT_UNSAFE_HOLD'
}
$payloadPending=New-Object 'System.Collections.Generic.Stack[string]'
$payloadPending.Push($payload)
while ($payloadPending.Count -gt 0) {
  $payloadDirectory=$payloadPending.Pop()
  Assert-E06PlainPathAncestors -Candidate $payloadDirectory -Scope 'NSIS_PAYLOAD_DIRECTORY'
  foreach ($childDirectory in @(Get-ChildItem -LiteralPath $payloadDirectory -Directory -Force -ErrorAction Stop)) {
    if (($childDirectory.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
      throw 'E06_NSIS_PAYLOAD_DIRECTORY_REPARSE_HOLD'
    }
    $payloadPending.Push($childDirectory.FullName)
  }
}
# Include the existing program files in the conservative NSIS manifest.
$entries=@(Get-ChildItem -LiteralPath $payload -File -Recurse -Force | Sort-Object FullName | ForEach-Object {
  if (($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'NO_REPARSE_PAYLOAD' }
  Assert-E06PlainPathAncestors -Candidate $_.FullName -Scope 'NSIS_PAYLOAD_FILE'
  $relative=$_.FullName.Substring($payload.Length).TrimStart('\')
  [ordered]@{path=$relative.Replace('\','/');bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
})
if ($IncludeMega814) {
  foreach ($expectedMenuAsset in @(
    'Assets/mega814/menu10.png',
    'Assets/mega814/mega814.mjs',
    'Assets/mega814/mega814.css',
    'Assets/mega814/menu-v2-193.json',
    'Assets/mega814/MEGA814_RECEIPT.json',
    'Assets/creative/wow200/ui/onehost-menu-bindings.mjs'
  )) {
    if (@($entries | Where-Object { $_.path -ceq $expectedMenuAsset }).Count -ne 1) {
      throw "MEGAB_MENU10_NSIS_MANIFEST_ASSET_MISSING:$expectedMenuAsset"
    }
  }
}
$manifest=[ordered]@{schema='NOX_P01_PAYLOAD_SHA256_V1';entrypoint='NOX.P01.Shell.exe';taskId='NOX-V16-E06-EXPRESS-ONEHOST';runId=$RunId;version='16.0.0';files=$entries}
$manifestPath=Join-Path $payload 'payload.sha256.json'
[IO.File]::WriteAllText($manifestPath,($manifest | ConvertTo-Json -Depth 7),(New-Object System.Text.UTF8Encoding($false)))
# W10 R105: original R11 SHA-locked verifier lacks installed-metadata mode.
# Reuse the already-reviewed original C09 verifier ONLY in the disposable R11
# installer stage. It extends strict owned-file checks to the two NSIS files
# required after /S and for C11 rollback; never patch the immutable 729 archive.
$reviewedVerifier=Join-Path $repoRoot 'stage/proposals/P01/C09/Installer/Verify-Payload.ps1'
$originalStagedVerifier=Join-Path $installer 'Verify-Payload.ps1'
Assert-E06PlainPathAncestors -Candidate $reviewedVerifier -Scope 'P01_C09_APPROVED_VERIFIER'
Assert-E06PlainPathAncestors -Candidate $originalStagedVerifier -Scope 'P01_R11_STAGED_VERIFIER'
$reviewedItem=Get-Item -LiteralPath $reviewedVerifier -Force -ErrorAction Stop
$stagedItem=Get-Item -LiteralPath $originalStagedVerifier -Force -ErrorAction Stop
if ($reviewedItem.PSIsContainer -or $stagedItem.PSIsContainer -or
    ($reviewedItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
    ($stagedItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
  throw 'P01_C09_APPROVED_VERIFIER_UNSAFE_PATH_HOLD'
}
$stagedOriginalSha=(Get-FileHash -LiteralPath $originalStagedVerifier -Algorithm SHA256).Hash.ToLowerInvariant()
if ($stagedOriginalSha -cne 'e741c131ddc1af45391ed64b4cdce686895aa78bd67e6bd4795fa97f548d455b') {
  throw 'P01_C09_ORIGINAL_R11_PREIMAGE_SHA_HOLD'
}
$reviewedGitBlob=((& $gitTool.Source -C $repoRoot hash-object -- $reviewedVerifier) | Out-String).Trim().ToLowerInvariant()
if ($LASTEXITCODE -ne 0 -or $reviewedGitBlob -cne '2fe86cad7e96eaf1a67354dfce3cf3f96dd33dfa') {
  throw 'P01_C09_APPROVED_VERIFIER_BLOB_HOLD'
}
$reviewedContent=[IO.File]::ReadAllText($reviewedVerifier)
foreach ($guard in @('[switch]$AllowInstalledMetadata', 'Assert-P01UniqueManifestMembers',
                    'Assert-NoReparseAncestors', 'invalid backup ownership marker',
                    'sha mismatch', 'file count mismatch', 'Uninstall.exe')) {
  if (!$reviewedContent.Contains($guard)) { throw 'P01_C09_APPROVED_VERIFIER_CONTRACT_HOLD' }
}
$reviewedSha=(Get-FileHash -LiteralPath $reviewedVerifier -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::Copy($reviewedVerifier,$originalStagedVerifier,$true)
$stagedApprovedSha=(Get-FileHash -LiteralPath $originalStagedVerifier -Algorithm SHA256).Hash.ToLowerInvariant()
if ($stagedApprovedSha -cne $reviewedSha) {
  throw 'P01_C09_DISPOSABLE_VERIFIER_READBACK_HOLD'
}
Write-Host "P01_C09_APPROVED_INSTALLED_METADATA_STAGE_PASS original_sha256=$stagedOriginalSha reviewed_git_blob=$reviewedGitBlob approved_sha256=$stagedApprovedSha"
# W01 R102: only the disposable SHA-verified original R11 verifier is adapted.
# The NSIS child Windows PowerShell 5.1 lacks Get-FileHash on the proven
# runner. Preserve original JSON/path/reparse/length/SHA and rollback checks.
$verifierPath=Join-Path $installer 'Verify-Payload.ps1'
Assert-E06PlainPathAncestors -Candidate $verifierPath -Scope 'P01_VERIFIER_COMPAT'
$verifierInfo=Get-Item -LiteralPath $verifierPath -Force -ErrorAction Stop
if ($verifierInfo.PSIsContainer -or
    ($verifierInfo.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
  throw 'P01_VERIFIER_COMPAT_UNSAFE_SOURCE_HOLD'
}
$verifierBefore=[IO.File]::ReadAllText($verifierPath)
$oldHash='  $actual = (Get-FileHash -LiteralPath $full -Algorithm SHA256).Hash.ToLowerInvariant()'
$oldHeader='$ErrorActionPreference = ''Stop'''
if (([regex]::Matches($verifierBefore,[regex]::Escape($oldHash))).Count -ne 1 -or
    ([regex]::Matches($verifierBefore,[regex]::Escape($oldHeader))).Count -ne 1 -or
    !$verifierBefore.Contains('P01_PAYLOAD_VERIFY_FAILED') -or
    !$verifierBefore.Contains('Assert-NoReparseAncestors') -or
    !$verifierBefore.Contains('sha mismatch') -or
    $verifierBefore.Contains('Get-P01VerifiedSha256')) {
  throw 'P01_VERIFIER_COMPAT_ORIGINAL_PREIMAGE_HOLD'
}
$nl=if ($verifierBefore.Contains(([string][char]13+[string][char]10))) {
  [string][char]13+[string][char]10
} else { [string][char]10 }
$hashHelper=@'
function Get-P01VerifiedSha256([string]$Path) {
  $inputStream=$null
  $digest=$null
  try {
    $inputStream=[IO.File]::Open($Path,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    $digest=[Security.Cryptography.SHA256]::Create()
    return ([BitConverter]::ToString($digest.ComputeHash($inputStream))).Replace('-','').ToLowerInvariant()
  } finally {
    if ($null -ne $digest) { $digest.Dispose() }
    if ($null -ne $inputStream) { $inputStream.Dispose() }
  }
}
'@
$hashHelper=$hashHelper.Replace(([string][char]13+[string][char]10),([string][char]10)).Replace(([string][char]10),$nl)
$verifierAfter=$verifierBefore.Replace($oldHeader,$oldHeader+$nl+$hashHelper+$nl).Replace(
  $oldHash,'  $actual = Get-P01VerifiedSha256 $full')
if ($verifierAfter -ceq $verifierBefore -or
    $verifierAfter.Contains($oldHash) -or
    ([regex]::Matches($verifierAfter,'Get-P01VerifiedSha256')).Count -ne 2) {
  throw 'P01_VERIFIER_COMPAT_TRANSFORM_HOLD'
}
$verifierBeforeSha=(Get-FileHash -LiteralPath $verifierPath -Algorithm SHA256).Hash.ToLowerInvariant()
[IO.File]::WriteAllText($verifierPath,$verifierAfter,(New-Object System.Text.UTF8Encoding($false)))
$verifierAfterSha=(Get-FileHash -LiteralPath $verifierPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($verifierBeforeSha -ceq $verifierAfterSha -or
    [IO.File]::ReadAllText($verifierPath) -cne $verifierAfter) {
  throw 'P01_VERIFIER_COMPAT_WRITE_READBACK_HOLD'
}
Write-Host "P01_PS51_DOTNET_SHA256_STAGED before=$verifierBeforeSha after=$verifierAfterSha ORIGINAL_SHA_CHECK_RETAINED"

# U09: The immutable R11 remover has a DIFFERENT lexical shape from the
# reviewed C09 remover; never guess a regex replacement for archived script.
# Reuse the already SHA/blob-pinned NX03 reviewed C09 TWO-PHASE NO-LOSS stage
# used by t06_package_original_onehost.py, in disposable R11 only.
$rmPath=Join-Path $installer 'Remove-InstalledPayload.ps1'
$rmReviewed=Join-Path $repoRoot 'stage/proposals/P01/C09/Installer/Remove-InstalledPayload.ps1'
$rmStageHelper=Join-Path $repoRoot 'coordination/e06/nx03_reviewed_uninstall_stage.py'
foreach ($candidate in @($rmPath,$rmReviewed,$rmStageHelper)) {
  Assert-E06PlainPathAncestors -Candidate $candidate -Scope 'P01_C09_REMOVER_STAGE'
  $item=Get-Item -LiteralPath $candidate -Force -ErrorAction Stop
  if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw 'P01_C09_REMOVER_STAGE_UNSAFE_PATH_HOLD'
  }
}
$rmReviewedBlob=((& $gitTool.Source -C $repoRoot hash-object -- $rmReviewed) | Out-String).Trim().ToLowerInvariant()
$rmHelperBlob=((& $gitTool.Source -C $repoRoot hash-object -- $rmStageHelper) | Out-String).Trim().ToLowerInvariant()
if ($LASTEXITCODE -ne 0 -or
    $rmReviewedBlob -cne 'fef0f6c5dd979cfa7c148169c18f278e7e72685d' -or
    $rmHelperBlob -cne '2b0ad8c67811f3d2309182327215b32953a9b23e') {
  throw 'P01_C09_REMOVER_REVIEWED_BLOB_HOLD'
}
$rmStageCode=@'
import json
import sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from nx03_reviewed_uninstall_stage import stage_reviewed_remove
print(json.dumps(stage_reviewed_remove(Path(sys.argv[2]),Path(sys.argv[3])),sort_keys=True))
'@
$rmStagePython=Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -First 1
if (!$rmStagePython) { throw 'P01_C09_REMOVER_PYTHON_TOOLCHAIN_REQUIRED' }
$rmOutput=(& $rmStagePython.Source -B -c $rmStageCode (Join-Path $repoRoot 'coordination/e06') $rmPath $rmReviewed 2>&1 | Out-String).Trim()
if ($LASTEXITCODE -ne 0) { throw 'P01_C09_REMOVER_REVIEWED_STAGE_HOLD' }
try { $rmProof=$rmOutput | ConvertFrom-Json -ErrorAction Stop }
catch { throw 'P01_C09_REMOVER_RECEIPT_JSON_HOLD' }
$rmReadback=(Get-FileHash -LiteralPath $rmPath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($rmProof.changed -ne $true -or
    $rmProof.original_donor_changed -ne $false -or
    $rmProof.original_r11_sha256 -cne '6853f3d4a32eb5946c3c68d22b0d61e3a402b729ebda225cd3f6b8b154b1ec55' -or
    $rmProof.reviewed_git_blob -cne $rmReviewedBlob -or
    $rmProof.staged_sha256 -cne $rmReadback -or
    $rmProof.release_accepted -ne $false -or
    $rmProof.independent_e07 -cne 'NOT_RUN') {
  throw 'P01_C09_REMOVER_RECEIPT_READBACK_HOLD'
}
Write-Host "NX03_C09_REVIEWED_REMOVE_STAGE_PASS original=$($rmProof.original_r11_sha256) stage=$rmReadback"

& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $installer 'Verify-Payload.ps1') -Root $payload -Manifest $manifestPath
if ($LASTEXITCODE -ne 0) { throw 'ORIGINAL_NSIS_PAYLOAD_SHA_GATE_HOLD' }
# C11: patch ONLY the disposable ORIGINAL NSIS source before makensis.
# An update must never rename an unverified current install into the sole
# rollback slot.  Original 729-file archive and Git source remain untouched.
$c11NsiPath=Join-Path $installer 'NOX-HELION-Setup.nsi'
Assert-E06PlainPathAncestors -Candidate $c11NsiPath -Scope 'NSIS_ROLLBACK'
$c11NsiOriginal=[IO.File]::ReadAllText($c11NsiPath)
$c11Anchor='  StagePayload:'
$c11Pos=$c11NsiOriginal.IndexOf($c11Anchor,[StringComparison]::Ordinal)
if ($c11Pos -lt 0 -or
    $c11NsiOriginal.LastIndexOf($c11Anchor,[StringComparison]::Ordinal) -ne $c11Pos -or
    !$c11NsiOriginal.Contains('Verify-Payload.ps1') -or
    !$c11NsiOriginal.Contains('Rename "$INSTDIR" "$BackupDir"') -or
    $c11NsiOriginal.Contains('C11OldPayloadChecked')) {
  throw 'C11_NSIS_OWNER_PREIMAGE_HOLD'
}
$c11Guard=@'
  ; C11: reject corrupt installed payload before extracting a new stage.
  ; Never strand a verified new StageDir on a failed old-payload check.
  IfFileExists "$INSTDIR\nox-p01-owned.txt" 0 C11OldPayloadChecked
  File "/oname=$PLUGINSDIR\Verify-Payload.ps1" "${VERIFY_SCRIPT}"
  nsExec::ExecToStack 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\Verify-Payload.ps1" -Root "$INSTDIR" -Manifest "$INSTDIR\payload.sha256.json" -AllowInstalledMetadata'
  Pop $ExitCode
  Pop $CheckResult
  ${If} $ExitCode != "0"
    DetailPrint "$CheckResult"
    Abort "Existing application payload is not rollback-safe; update refused."
  ${EndIf}
  C11OldPayloadChecked:
'@
$c11Eol=if ($c11NsiOriginal.Contains("`r`n")) { "`r`n" } else { "`n" }
$c11Guard=[regex]::Replace($c11Guard,'\r?\n',$c11Eol)
$c11NsiPatched=$c11NsiOriginal.Substring(0,$c11Pos)+
                $c11Guard+$c11Eol+
                $c11NsiOriginal.Substring($c11Pos)
if ($c11NsiPatched.IndexOf('C11OldPayloadChecked:',[StringComparison]::Ordinal) -lt 0) {
  throw 'C11_NSIS_ROLLBACK_FENCE_STAGE_HOLD'
}
# W04 R108: original R11 NSIS UninstallString emits warning 6000 due to
# backslash-escaped quotes. Stage the officially documented quote form ONLY
# in the disposable R11 source; original 729 archive remains immutable.
$uninstallRegistryBad='  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "UninstallString" ''\"$INSTDIR\Uninstall.exe\"'''
$uninstallRegistryApproved='  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "UninstallString" ''"$INSTDIR\Uninstall.exe"'''
# R113: immutable original R11 7308-byte preimage, line 124 length 129,
# SHA256 6ab87005e57b21c50252b13173784aafc348aeff3953aef60e1226f6154651d4.
# Admit ONLY five exact reviewed literal values; unknown/multiple HOLD.
$uninstallRegistryHold='P01_NSIS_UNINSTALL_REGISTRY_PREIMAGE_HOLD'
$uninstallRegistryLinePattern='(?m)^[ \t]*WriteRegStr[ \t]+[^\r\n]*"UninstallString"[ \t]+[^\r\n]*'
$uninstallRegistryMatches=[regex]::Matches($c11NsiPatched,$uninstallRegistryLinePattern)
if ($uninstallRegistryMatches.Count -ne 1) { throw $uninstallRegistryHold }
$uninstallRegistryMatch=$uninstallRegistryMatches[0]
$uninstallRegistryBody=$uninstallRegistryMatch.Value.TrimStart()
$uninstallRegistryApprovedBody=$uninstallRegistryApproved.TrimStart()
$uninstallRegistryValueAt=$uninstallRegistryApprovedBody.IndexOf('"UninstallString" ',[StringComparison]::Ordinal)
if ($uninstallRegistryValueAt -lt 0) { throw $uninstallRegistryHold }
$uninstallRegistryKey=$uninstallRegistryApprovedBody.Substring(0,$uninstallRegistryValueAt+'"UninstallString" '.Length)
$uninstallRegistryAllowed=@(
  $uninstallRegistryBad.TrimStart(),
  $uninstallRegistryApprovedBody,
  ($uninstallRegistryKey + '"\"$INSTDIR\Uninstall.exe\""'),
  ($uninstallRegistryKey + '"$INSTDIR\Uninstall.exe"'),
  ($uninstallRegistryKey + [char]39 + '$"$INSTDIR\Uninstall.exe$"' + [char]39)
)
if ($uninstallRegistryAllowed -cnotcontains $uninstallRegistryBody) {
  throw $uninstallRegistryHold
}
$uninstallRegistryIndent=$uninstallRegistryMatch.Value.Substring(0,$uninstallRegistryMatch.Value.Length-$uninstallRegistryBody.Length)
$uninstallRegistryReplacement=$uninstallRegistryIndent+$uninstallRegistryApprovedBody
$c11NsiPatched=$c11NsiPatched.Substring(0,$uninstallRegistryMatch.Index)+
               $uninstallRegistryReplacement+
               $c11NsiPatched.Substring($uninstallRegistryMatch.Index+$uninstallRegistryMatch.Length)
$uninstallRegistryReadback=[regex]::Matches($c11NsiPatched,$uninstallRegistryLinePattern)
if ($uninstallRegistryReadback.Count -ne 1 -or
    $uninstallRegistryReadback[0].Value -cne $uninstallRegistryReplacement) {
  throw 'P01_NSIS_UNINSTALL_REGISTRY_QUOTE_HOLD'
}
Write-Host 'P01_NSIS_UNINSTALL_REGISTRY_QUOTE_STAGE_PASS'
[IO.File]::WriteAllText($c11NsiPath,$c11NsiPatched,(New-Object System.Text.UTF8Encoding($false)))
Write-Host "C11_NSIS_ROLLBACK_OLD_PAYLOAD_SHA_GATE_STAGED"
$setup=Join-Path $out 'NOX-HELION-V16-DIAGNOSTIC-SETUP.exe'
& $makensisPath /V2 "/DPAYLOAD_DIR=$payload" "/DVERIFY_SCRIPT=$(Join-Path $installer 'Verify-Payload.ps1')" "/DPREFLIGHT_SCRIPT=$(Join-Path $installer 'Preflight-InstallPath.ps1')" "/DREMOVE_SCRIPT=$(Join-Path $installer 'Remove-InstalledPayload.ps1')" "/DOUTPUT_SETUP=$setup" '/DAPP_VERSION=16.0.0' (Join-Path $installer 'NOX-HELION-Setup.nsi')
if ($LASTEXITCODE -ne 0 -or !(Test-Path -LiteralPath $setup -PathType Leaf)) { throw 'EXISTING_OWNER_NSIS_COMPILER_HOLD' }
$sha=(Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash.ToLowerInvariant()
$wpf=Join-Path $payload 'NOX.P01.Shell.exe'
# A receipt may not relabel an older binary after another owner moves HEAD.
$e06HeadAtReceipt=((& git -C $e06RepoRoot rev-parse HEAD) | Out-String).Trim().ToLowerInvariant()
if ($LASTEXITCODE -ne 0 -or $e06HeadAtReceipt -cne $e06SourceHead) { throw 'E06_SOURCE_HEAD_CHANGED_DURING_BUILD' }
# A tracked owner edit during compilation invalidates this build's frozen-source claim.
# Disposable archive and output directories remain outside the tracked source set.
& git -C $e06RepoRoot diff --quiet --exit-code HEAD --
if ($LASTEXITCODE -ne 0) { throw 'E06_TRACKED_CHECKOUT_DIRTY_AT_RECEIPT' }
$receipt=[ordered]@{
 schema='NOX-E06-ONEHOST-DIAGNOSTIC-NSIS-v1';run_id=$RunId;owner=6;
 source_commit_sha1=$e06SourceHead;
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
