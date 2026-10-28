# E06 R14: no-loss repackage immutable WPF+original Python payload with exact owner P01 NSIS source.
# Runs on an isolated Windows GitHub runner; no production/user installation and no source rewrite.
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if($env:CI -cne 'true' -or $env:RUNNER_OS -cne 'Windows'){throw 'E06_R14_CI_ONLY'}
$dir=Join-Path (Get-Location) 'e06-r14-output'
New-Item -ItemType Directory -Path $dir -Force | Out-Null
$receipt=[ordered]@{
 schema='NOX_E06_R14_EXACT_OWNER_REPACK_V1';runId="E06-R14-$env:GITHUB_RUN_ID";
 sourceFrozenSetupSha256='ba0b96ecc3e05eb79a773e3147157e597711777ba42a917016aae990aeb0d554';
 frozenArtifactId=12783517896;frozenArtifactRun=40611662850;
 ownerP01HeadGitSha1='8e42bb15aecbee8412c342b0e9049b6cce044297';
 expectedOriginalPythonExeSha256='4e488372cf3f6410d268a7ef72b3e4b359a7a3e6642c7a16ac2e6f7eb06fc5f3';
 originalManifestSha256=$null;manifestFiles=$null;manifestVerified=$false;
 compiledSetupSha256=$null;compiledSetupBytes=$null;setupExitCode=$null;
 installedMarker=$false;installedWpf=$false;installedPython=$false;pythonDiagnose='NOT_RUN';
 stage='HOLD';failure=$null;sourceDeleted=$false;originalChanged=$false;
 ownerAcceptance=false;E07Accepted=$false;releaseAccepted=$false
}
try {
 $meta=gh api repos/MSSTXNEWS/nox-helion-pp-private-build/actions/artifacts/12783517896 | ConvertFrom-Json
 if($meta.id -ne 12783517896 -or $meta.expired -or
    $meta.workflow_run.id -ne 40611662850 -or
    $meta.workflow_run.head_sha -cne 'e5c50ca6c5db18d75b15c392155b3951a81df6f5'){throw 'E06_R14_FROZEN_PROVENANCE_HOLD'}
 $download=Join-Path $dir 'input'
 New-Item -ItemType Directory -Path $download -Force | Out-Null
 gh run download 40611662850 --repo MSSTXNEWS/nox-helion-pp-private-build --name nox-e06-onehost-installer-40611662850 --dir $download
 if($LASTEXITCODE -ne 0){throw 'E06_R14_ARTIFACT_FETCH_HOLD'}
 $setup=(Resolve-Path (Join-Path $download 'onehost-candidate/NOX-HELION-V16-DIAGNOSTIC-SETUP.exe')).Path
 if((Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash.ToLowerInvariant() -cne $receipt.sourceFrozenSetupSha256){
   throw 'E06_R14_FROZEN_SETUP_SHA_HOLD'
 }
 $sevenZip=Get-Command 7z.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
 if(!$sevenZip){throw 'E06_R14_7ZIP_UNAVAILABLE'}
 $extracted=Join-Path $dir 'frozen-extracted-read-only'
 New-Item -ItemType Directory -Path $extracted -Force | Out-Null
 & $sevenZip.Source x $setup "-o$extracted" -y | Out-Null
 if($LASTEXITCODE -ne 0){throw 'E06_R14_FROZEN_SETUP_EXTRACTION_FAIL'}
 $found=@(Get-ChildItem -LiteralPath $extracted -File -Recurse -Filter 'payload.sha256.json')
 if($found.Count -ne 1){throw "E06_R14_SOURCE_MANIFEST_COUNT_$($found.Count)"}
 $source=Split-Path $found[0].FullName -Parent
 if(!(Test-Path -LiteralPath (Join-Path $source 'NOX.P01.Shell.exe') -PathType Leaf)){throw 'E06_R14_SOURCE_WPF_MISSING'}
 $raw=[IO.File]::ReadAllBytes($found[0].FullName)
 $receipt.originalManifestSha256=(Get-FileHash -LiteralPath $found[0].FullName -Algorithm SHA256).Hash.ToLowerInvariant()
 $manifest=([Text.Encoding]::UTF8.GetString($raw))|ConvertFrom-Json
 if($manifest.schema -cne 'NOX_P01_PAYLOAD_SHA256_V1' -or $manifest.entrypoint -cne 'NOX.P01.Shell.exe'){
   throw 'E06_R14_MANIFEST_CONTRACT_HOLD'
 }
 $clean=Join-Path $dir 'payload-repacked-byte-exact'
 New-Item -ItemType Directory -Path $clean -Force | Out-Null
 $seen=New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
 foreach($file in @($manifest.files)){
   $rel=[string]$file.path
   if([string]::IsNullOrWhiteSpace($rel) -or $rel -match '(^|[\\/])\.\.($|[\\/])|[:*?"<>|]' -or
      [IO.Path]::IsPathRooted($rel) -or !$seen.Add($rel)){
      throw "E06_R14_UNSAFE_MANIFEST_ENTRY:$rel"
   }
   $src=Join-Path $source $rel
   if(!(Test-Path -LiteralPath $src -PathType Leaf)){throw "E06_R14_MISSING_MANIFEST_FILE:$rel"}
   $srcItem=Get-Item -LiteralPath $src -Force
   if(($srcItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){throw 'E06_R14_REPARSE_SOURCE_HOLD'}
   if((Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash.ToLowerInvariant() -cne [string]$file.sha256){
     throw "E06_R14_SOURCE_PAYLOAD_SHA_HOLD:$rel"
   }
   $dest=Join-Path $clean $rel
   New-Item -ItemType Directory -Path (Split-Path $dest -Parent) -Force | Out-Null
   Copy-Item -LiteralPath $src -Destination $dest
   if((Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash.ToLowerInvariant() -cne [string]$file.sha256){
     throw "E06_R14_DEST_PAYLOAD_SHA_HOLD:$rel"
   }
 }
 Copy-Item -LiteralPath $found[0].FullName -Destination (Join-Path $clean 'payload.sha256.json')
 $receipt.manifestFiles=$seen.Count
 $receipt.manifestVerified=$true
 if((Get-FileHash -LiteralPath (Join-Path $clean 'Backend/NOX_HELION_PRIVATE_CANDIDATE.exe') -Algorithm SHA256).Hash.ToLowerInvariant() -cne
    $receipt.expectedOriginalPythonExeSha256){throw 'E06_R14_PYTHON_ORIGINAL_SHA_HOLD'}
 $installer=Join-Path $dir 'owner1-pinned-installer-scripts'
 New-Item -ItemType Directory -Path $installer -Force | Out-Null
 $sourcePath='stage/proposals/P01/C09/Installer/'
 $names=@('NOX-HELION-Setup.nsi','Preflight-InstallPath.ps1','Verify-Payload.ps1','Remove-InstalledPayload.ps1')
 foreach($name in $names){
   $url="repos/MSSTXNEWS/nox-helion-pp-private-build/contents/$($sourcePath)$($name)?ref=$($receipt.ownerP01HeadGitSha1)"
   $record=gh api $url | ConvertFrom-Json
   if(!$record.content -or $record.type -cne 'file'){throw "E06_R14_OWNER_FILE_NOT_FOUND:$name"}
   $bytes=[Convert]::FromBase64String(($record.content -replace '\s',''))
   [IO.File]::WriteAllBytes((Join-Path $installer $name),$bytes)
   if($name -ceq 'Preflight-InstallPath.ps1' -and $record.sha -cne 'eb45add5a929eee99bc09ef87f2db3735556b78b'){
     throw 'E06_R14_OWNER1_PREFLIGHT_SHA1_DRIFT'
   }
 }
 & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File (Join-Path $installer 'Verify-Payload.ps1') -Root $clean -Manifest (Join-Path $clean 'payload.sha256.json')
 if($LASTEXITCODE -ne 0){throw 'E06_R14_OWNER1_PAYLOAD_VERIFICATION_HOLD'}
 $nsis=Get-Command makensis.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
 if(!$nsis){
   choco install nsis --version=3.11 --no-progress -y
   if($LASTEXITCODE -ne 0){throw 'E06_R14_PINNED_NSIS_UNAVAILABLE'}
   $exe= @('C:\Program Files (x86)\NSIS\makensis.exe','C:\Program Files\NSIS\makensis.exe')|
          Where-Object{Test-Path -LiteralPath $_ -PathType Leaf}|Select-Object -First 1
   if(!$exe){throw 'E06_R14_NSIS_EXE_UNAVAILABLE'}
 } else {$exe=$nsis.Source}
 $newSetup=Join-Path $dir 'NOX-HELION-R14-DIAGNOSTIC-ONEHOST-SETUP.exe'
 & $exe /V2 "/DPAYLOAD_DIR=$clean" "/DVERIFY_SCRIPT=$(Join-Path $installer 'Verify-Payload.ps1')" "/DPREFLIGHT_SCRIPT=$(Join-Path $installer 'Preflight-InstallPath.ps1')" "/DREMOVE_SCRIPT=$(Join-Path $installer 'Remove-InstalledPayload.ps1')" "/DOUTPUT_SETUP=$newSetup" '/DAPP_VERSION=16.0.1' (Join-Path $installer 'NOX-HELION-Setup.nsi')
 if($LASTEXITCODE -ne 0 -or !(Test-Path -LiteralPath $newSetup -PathType Leaf)){throw 'E06_R14_NSIS_REPACK_COMPILE_HOLD'}
 $receipt.compiledSetupSha256=(Get-FileHash -LiteralPath $newSetup -Algorithm SHA256).Hash.ToLowerInvariant()
 $receipt.compiledSetupBytes=(Get-Item -LiteralPath $newSetup).Length
 $root=Join-Path $env:LOCALAPPDATA 'Programs\NOX HELION'
 foreach($x in @($root,($root+'.__p01_stage'),($root+'.__p01_previous'),($root+'.__p01_rollback_saved'))){
   if(Test-Path -LiteralPath $x){throw 'E06_R14_PREEXISTING_USER_INSTALL_HOLD'}
 }
 $p=Start-Process -FilePath $newSetup -ArgumentList '/S' -PassThru
 if(!$p.WaitForExit(180000)){if(!$p.HasExited){$p.Kill($true)};throw 'E06_R14_INSTALL_TIMEOUT_HOLD'}
 $receipt.setupExitCode=$p.ExitCode
 $receipt.installedMarker=Test-Path -LiteralPath (Join-Path $root 'nox-p01-owned.txt') -PathType Leaf
 $receipt.installedWpf=Test-Path -LiteralPath (Join-Path $root 'NOX.P01.Shell.exe') -PathType Leaf
 $backend=Join-Path $root 'Backend/NOX_HELION_PRIVATE_CANDIDATE.exe'
 $receipt.installedPython=Test-Path -LiteralPath $backend -PathType Leaf
 if($p.ExitCode -ne 0 -or !$receipt.installedMarker -or !$receipt.installedWpf -or !$receipt.installedPython){
   throw "E06_R14_NATIVE_INSTALL_HOLD_$($p.ExitCode)"
 }
 if((Get-FileHash -LiteralPath $backend -Algorithm SHA256).Hash.ToLowerInvariant() -cne $receipt.expectedOriginalPythonExeSha256){throw 'E06_R14_INSTALLED_BACKEND_SHA_HOLD'}
 $o=Join-Path $env:RUNNER_TEMP 'E06-R14-Python-Diag-Output.txt'
 $e=Join-Path $env:RUNNER_TEMP 'E06-R14-Python-Diag-Error.txt'
 $b=Start-Process -FilePath $backend -ArgumentList '--diagnose' -RedirectStandardOutput $o -RedirectStandardError $e -PassThru
 if(!$b.WaitForExit(60000)){if(!$b.HasExited){$b.Kill($true)};throw 'E06_R14_PYTHON_RUNTIME_TIMEOUT'}
 if($b.ExitCode -ne 0){throw 'E06_R14_PYTHON_RUNTIME_EXIT_HOLD'}
 $diag=([IO.File]::ReadAllText($o)|ConvertFrom-Json)
 if([int]$diag.routes_total -lt 1 -or @($diag.cores).Count -ne 8){throw 'E06_R14_PYTHON_8_CORE_CONTRACT_HOLD'}
 $receipt.pythonDiagnose='PASS'
 $receipt.stage='NATIVE_COMBINED_DIAGNOSTIC_INSTALL_PASS_NOT_RELEASE'
 Write-Host 'E06_R14_REPACKED_ORIGINAL_WPF_PYTHON_REAL_WINDOWS_INSTALL_PASS'
} catch {
 $receipt.failure=$_.Exception.Message
 Write-Warning ("E06_R14_HOLD: "+$receipt.failure)
} finally {
 [IO.File]::WriteAllText((Join-Path $dir 'E06_R14_REPACK_RECEIPT.json'),($receipt|ConvertTo-Json -Depth 10),[Text.UTF8Encoding]::new($false))
 Write-Host ($receipt|ConvertTo-Json -Depth 10)
}
if($receipt.stage -cne 'NATIVE_COMBINED_DIAGNOSTIC_INSTALL_PASS_NOT_RELEASE'){throw 'E06_R14_NATIVE_REPACK_GATE_HOLD'}
