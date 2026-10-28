# E06 R14 read-only forensic diagnostic, same binary SHA. On disposable CI only.
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'; Set-StrictMode -Version Latest
if($env:CI -cne 'true' -or $env:RUNNER_OS -cne 'Windows'){throw 'E06_CI_ONLY'}
$expected='45083b25458a4abf4f7d8863a04093ed5adeeff7ea3d2ba65dbabeda88e5bf02'
$out='e06-r14-forensic-receipt.json'
$receipt=[ordered]@{
 schema='NOX_E06_R14_EXACT_REPACK_FORENSIC_V1';setupSha256Expected=$expected;
 setupSha256Actual=$null;runId=$env:GITHUB_RUN_ID;
 ownerP01SHA1='8e42bb15aecbee8412c342b0e9049b6cce044297';
 extractedPreflightSha256=$null; directPreflight='NOT_RUN'; directExitCode=$null;
 directOutput=$null;probeNsisExitCode=$null;probeResult=$null;probeOutput=$null;
 sourceModified=$false;userDataModified=$false;status='HOLD';failure=$null
}
try {
 $download=Join-Path $env:RUNNER_TEMP 'e06-r14-frozen-forensic-input'
 New-Item -ItemType Directory $download -Force|Out-Null
 $metadata=gh api repos/MSSTXNEWS/nox-helion-pp-private-build/actions/artifacts/12784014910 | ConvertFrom-Json
 if($metadata.id -ne 12784014910 -or $metadata.expired -or $metadata.workflow_run.id -ne 40615066030){throw 'E06_R14_FOR_FIXTURE_ARTIFACT_PROVENANCE_HOLD'}
 gh run download 40615066030 --repo MSSTXNEWS/nox-helion-pp-private-build --name nox-e06-r14-repack-40615066030 --dir $download
 if($LASTEXITCODE -ne 0){throw 'E06_R14_DOWNLOAD_FAILED'}
 $setups=@(Get-ChildItem -LiteralPath $download -Recurse -File -Filter 'NOX-HELION-R14-DIAGNOSTIC-ONEHOST-SETUP.exe')
 if($setups.Count -ne 1){throw "E06_R14_SETUP_COUNT_$($setups.Count)"}
 $setup=$setups[0].FullName
 $receipt.setupSha256Actual=(Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash.ToLowerInvariant()
 if($receipt.setupSha256Actual -cne $expected){throw 'E06_R14_SETUP_SHA_HOLD'}
 $zip=Get-Command 7z.exe -CommandType Application -ErrorAction Stop|Select-Object -First 1
 $extract=Join-Path $env:RUNNER_TEMP 'e06-r14-bundled-preflight'
 New-Item -ItemType Directory -Path $extract -Force|Out-Null
 & $zip.Source x $setup "-o$extract" -y|Out-Null
 if($LASTEXITCODE -ne 0){throw 'E06_R14_7ZIP_EXTRACT_FAILED'}
 $ps=@(Get-ChildItem -LiteralPath $extract -File -Recurse -Filter 'Preflight-InstallPath.ps1')
 if($ps.Count -ne 1){throw "E06_R14_BUNDLED_PREFLIGHT_COUNT_$($ps.Count)"}
 $preflight=$ps[0].FullName
 $receipt.extractedPreflightSha256=(Get-FileHash -LiteralPath $preflight -Algorithm SHA256).Hash.ToLowerInvariant()
 $root=Join-Path $env:LOCALAPPDATA 'Programs\NOX HELION'
 if(Test-Path -LiteralPath $root){throw 'E06_R14_UNEXPECTED_PREEXISTING_INSTALL'}
 $output=@(& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $preflight -InstallRoot $root 2>&1)
 $receipt.directExitCode=$LASTEXITCODE
 $receipt.directOutput=($output|Out-String).Substring(0,[Math]::Min(1200,($output|Out-String).Length))
 $receipt.directPreflight=if($LASTEXITCODE -eq 0 -and $output -contains 'P01_PREFLIGHT_PASS'){'PASS'}else{'HOLD'}
 Write-Host "E06_R14_DIRECT_BUNDLED_PREFLIGHT_$($receipt.directPreflight)"
 # Isolate exact NSIS nsExec shell handoff without installing the 139MB payload.
 $probeNsi=Join-Path $env:RUNNER_TEMP 'E06-R14-NSIS-NSEXEC-PROBE.nsi'
 $probeExe=Join-Path $env:RUNNER_TEMP 'E06-R14-NSIS-NSEXEC-PROBE.exe'
 $probeOut=Join-Path $env:RUNNER_TEMP 'E06-R14-NSIS-NSEXEC-PROBE-OUTPUT.txt'
 $nsi=@'
 Unicode true
 RequestExecutionLevel user
 SilentInstall silent
 OutFile "__PROBE_EXE__"
 Section
  InitPluginsDir
  File "/oname=$PLUGINSDIR\Preflight-InstallPath.ps1" "__PREFLIGHT__"
  nsExec::ExecToStack 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\Preflight-InstallPath.ps1" -InstallRoot "$LOCALAPPDATA\Programs\NOX HELION"'
  Pop $0
  Pop $1
  FileOpen $2 "__PROBE_OUT__" w
  FileWrite $2 "ExitCode=$0$\r$\n"
  FileWrite $2 "Output=$1$\r$\n"
  FileClose $2
 SectionEnd
 '@
 $nsi=$nsi.Replace('__PROBE_EXE__',$probeExe).Replace('__PREFLIGHT__',$preflight).Replace('__PROBE_OUT__',$probeOut)
 [IO.File]::WriteAllText($probeNsi,$nsi,[Text.UTF8Encoding]::new($false))
 $makensis=Get-Command makensis.exe -CommandType Application -ErrorAction SilentlyContinue|Select-Object -First 1
 if(!$makensis){$candidate='C:\Program Files (x86)\NSIS\makensis.exe';if(!(Test-Path -LiteralPath $candidate)){throw 'E06_R14_MAKENSIS_MISSING'};$makensis=Get-Item $candidate}
 $makensisPath=if($makensis -is [IO.FileInfo]){$makensis.FullName}else{$makensis.Source}
 & $makensisPath /V2 $probeNsi
 if($LASTEXITCODE -ne 0){throw 'E06_R14_MINIMAL_NSEXEC_COMPILE_FAILED'}
 $process=Start-Process -FilePath $probeExe -ArgumentList '/S' -Wait -PassThru
 $receipt.probeNsisExitCode=$process.ExitCode
 if(Test-Path -LiteralPath $probeOut -PathType Leaf){
  $receipt.probeOutput=([IO.File]::ReadAllText($probeOut)).Substring(0,[Math]::Min(1200,([IO.File]::ReadAllText($probeOut)).Length))
 }
 $receipt.status='FORENSIC_DIAGNOSTIC_CAPTURED_NOT_INSTALL_ACCEPTANCE'
 Write-Host 'E06_R14_NSEXEC_FORENSIC_CAPTURED'
}catch{
 $receipt.failure=$_.Exception.Message
 Write-Warning ('E06_R14_FORENSIC_HOLD '+$receipt.failure)
}finally{
 [IO.File]::WriteAllText((Join-Path (Get-Location) $out),($receipt|ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
 Write-Host ($receipt|ConvertTo-Json -Depth 8)
}
if($receipt.status -cne 'FORENSIC_DIAGNOSTIC_CAPTURED_NOT_INSTALL_ACCEPTANCE'){throw 'E06_R14_FORENSIC_NOT_CAPTURED'}
