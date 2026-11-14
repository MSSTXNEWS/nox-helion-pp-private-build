# E06 R17 - read-only proof of native NSIS nsExec return vs direct PowerShell on EXACT setup.
# CI-only, no user installation, no source alteration, keep release gate closed.
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if ($env:CI -cne 'true' -or $env:RUNNER_OS -cne 'Windows') { throw 'E06_R17_CI_ONLY' }
$expected = '45083b25458a4abf4f7d8863a04093ed5adeeff7ea3d2ba65dbabeda88e5bf02'
$receipt=[ordered]@{
 schema='NOX_E06_R17_NSIS_NSEXEC_PROBE_V1';runId=$env:GITHUB_RUN_ID;
 originalRepackArtifactId=12784014910; originalRun=40615066030;
 expectedSetupSha256=$expected;actualSetupSha256=$null;preflightSha256=$null;
 directPreflightExit=$null;directPreflightOutput=$null;
 directVerifyExit=$null;directVerifyOutput=$null;
 nsExecProbeExit=$null;nsExecProbeOutput=$null;
 sourceOriginalChanged=$false;userInstallationPerformed=$false;
 status='HOLD';reason=$null;releaseAllowed=$false
}
$out='e06-r17-nsexec-receipt.json'
try {
  $download=Join-Path $env:RUNNER_TEMP 'E06-R17-Frozen'
  if(Test-Path -LiteralPath $download){throw 'E06_R17_EXISTING_TMP_HOLD'}
  New-Item -ItemType Directory -Path $download | Out-Null
  $m=gh api repos/MSSTXNEWS/nox-helion-pp-private-build/actions/artifacts/12784014910 | ConvertFrom-Json
  if($m.id -ne 12784014910 -or $m.expired -or $m.workflow_run.id -ne 40615066030){throw 'E06_R17_ARTIFACT_PROVENANCE_HOLD'}
  gh run download 40615066030 --repo MSSTXNEWS/nox-helion-pp-private-build --name nox-e06-r14-repack-40615066030 --dir $download
  if($LASTEXITCODE -ne 0){throw 'E06_R17_ARTIFACT_DOWNLOAD_HOLD'}
  $list=@(Get-ChildItem -LiteralPath $download -Recurse -File -Filter 'NOX-HELION-R14-DIAGNOSTIC-ONEHOST-SETUP.exe')
  if($list.Count -ne 1){throw 'E06_R17_EXACT_SETUP_COUNT_HOLD'}
  $setup=$list[0].FullName
  $receipt.actualSetupSha256=(Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash.ToLowerInvariant()
  if($receipt.actualSetupSha256 -cne $expected){throw 'E06_R17_SETUP_SHA_MISMATCH'}
  $zip=Get-Command 7z.exe -CommandType Application -ErrorAction Stop | Select-Object -First 1
  $stage=Join-Path $env:RUNNER_TEMP 'E06-R17-EXTRACTED-STAGE'
  if(Test-Path -LiteralPath $stage){throw 'E06_R17_STAGE_EXISTS_HOLD'}
  New-Item -ItemType Directory -Path $stage | Out-Null
  & $zip.Source x $setup "-o$stage" -y | Out-Null
  if($LASTEXITCODE -ne 0){throw 'E06_R17_EXTRACTION_HOLD'}
  $preflights=@(Get-ChildItem -LiteralPath $stage -Recurse -File -Filter 'Preflight-InstallPath.ps1')
  $verifiers=@(Get-ChildItem -LiteralPath $stage -Recurse -File -Filter 'Verify-Payload.ps1')
  $manifests=@(Get-ChildItem -LiteralPath $stage -Recurse -File -Filter 'payload.sha256.json')
  if($preflights.Count -ne 1 -or $verifiers.Count -ne 1 -or $manifests.Count -ne 1){throw 'E06_R17_EMBEDDED_FILE_COUNT_HOLD'}
  $receipt.preflightSha256=(Get-FileHash -LiteralPath $preflights[0].FullName -Algorithm SHA256).Hash.ToLowerInvariant()
  $installRoot=Join-Path $env:LOCALAPPDATA 'Programs\NOX HELION'
  if(Test-Path -LiteralPath $installRoot){throw 'E06_R17_USER_INSTALL_EXISTS_HOLD'}
  $direct=@(& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $preflights[0].FullName -InstallRoot $installRoot 2>&1)
  $receipt.directPreflightExit=$LASTEXITCODE
  $receipt.directPreflightOutput=($direct|Out-String).Substring(0,[Math]::Min(400,($direct|Out-String).Length))
  $payloadRoot=Split-Path $manifests[0].FullName -Parent
  $verify=@(& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $verifiers[0].FullName -Root $payloadRoot -Manifest $manifests[0].FullName 2>&1)
  $receipt.directVerifyExit=$LASTEXITCODE
  $receipt.directVerifyOutput=($verify|Out-String).Substring(0,[Math]::Min(400,($verify|Out-String).Length))
  $makensis=Get-Command makensis.exe -CommandType Application -ErrorAction SilentlyContinue|Select-Object -First 1
  if($null -eq $makensis){$candidate='C:\Program Files (x86)\NSIS\makensis.exe';if(!(Test-Path -LiteralPath $candidate)){throw 'E06_R17_NSIS_UNAVAILABLE'};$makensis=Get-Item $candidate}
  $compiler=if($makensis -is [IO.FileInfo]){$makensis.FullName}else{$makensis.Source}
  $probe=Join-Path $env:RUNNER_TEMP 'E06-R17-NSIS-VERIFY-PROBE.nsi'
  $exe=Join-Path $env:RUNNER_TEMP 'E06-R17-NSIS-VERIFY-PROBE.exe'
  $log=Join-Path $env:RUNNER_TEMP 'E06-R17-NSIS-VERIFY-RESULT.txt'
  $lines=@(
    'Unicode true'
    'RequestExecutionLevel user'
    'SilentInstall silent'
    'OutFile "__EXE__"'
    'Section'
    '  InitPluginsDir'
    '  File "/oname=$PLUGINSDIR\Verify-Payload.ps1" "__SCRIPT__"'
    '  nsExec::ExecToStack ''powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\Verify-Payload.ps1" -Root "__ROOT__" -Manifest "__MANIFEST__"'''
    '  Pop $0'
    '  Pop $1'
    '  FileOpen $2 "__LOG__" w'
    '  FileWrite $2 "NSIS_NSEXEC_CODE=$0$\r$\n"'
    '  FileWrite $2 "NSIS_NSEXEC_STDOUT=$1$\r$\n"'
    '  FileClose $2'
    'SectionEnd'
  )
  $text=($lines -join [Environment]::NewLine).Replace('__EXE__',$exe).Replace('__SCRIPT__',$verifiers[0].FullName).Replace('__ROOT__',$payloadRoot).Replace('__MANIFEST__',$manifests[0].FullName).Replace('__LOG__',$log)
  [IO.File]::WriteAllText($probe,$text,[Text.UTF8Encoding]::new($false))
  & $compiler /V2 $probe
  if($LASTEXITCODE -ne 0){throw 'E06_R17_MINIMAL_NSIS_COMPILE_HOLD'}
  $proc=Start-Process -FilePath $exe -ArgumentList '/S' -PassThru
  if(!$proc.WaitForExit(180000)){if(!$proc.HasExited){$proc.Kill($true)};throw 'E06_R17_NSEXEC_TIMEOUT_HOLD'}
  $receipt.nsExecProbeExit=$proc.ExitCode
  if(Test-Path -LiteralPath $log -PathType Leaf){$receipt.nsExecProbeOutput=([IO.File]::ReadAllText($log)).Substring(0,[Math]::Min(800,([IO.File]::ReadAllText($log)).Length))}
  $receipt.status='FORENSIC_CAPTURED_NOT_INSTALL_ACCEPTANCE'
  Write-Host 'E06_R17_EXACT_NSEXEC_FORENSIC_CAPTURED'
} catch {
  $receipt.reason=$_.Exception.Message
  Write-Warning ('E06_R17_HOLD '+$receipt.reason)
} finally {
 [IO.File]::WriteAllText((Join-Path (Get-Location) $out),($receipt|ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
 Write-Host ($receipt|ConvertTo-Json -Depth 8)
}
if($receipt.status -cne 'FORENSIC_CAPTURED_NOT_INSTALL_ACCEPTANCE'){throw 'E06_R17_FORENSIC_HOLD'}
