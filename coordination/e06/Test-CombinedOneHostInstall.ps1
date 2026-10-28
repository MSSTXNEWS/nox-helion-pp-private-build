# E06 R13. Actual frozen combined WPF+Python NSIS install on disposable Windows CI only.
# Never repair or delete pre-existing directories; abort with HOLD instead.
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if($env:CI -cne 'true' -or $env:RUNNER_OS -cne 'Windows'){throw 'E06_CI_ONLY'}
$receipt=[ordered]@{
 schema='NOX_E06_R13_COMBINED_NSIS_RUNTIME_V1';runId="E06-R13-$env:GITHUB_RUN_ID";
 sourceHead=$env:GITHUB_SHA;installerSourceRun=40611662850;
 setupExpectedSha256='ba0b96ecc3e05eb79a773e3147157e597711777ba42a917016aae990aeb0d554';
 backendExpectedSha256='4e488372cf3f6410d268a7ef72b3e4b359a7a3e6642c7a16ac2e6f7eb06fc5f3';
 setupActualSha256=$null;setupExitCode=$null;
 stageExists=$null;installedMarker=$false;wpfExecutable=$false;
 originalPythonShaValid=$false;pythonDiagnose='NOT_RUN';pythonRoutes=$null;pythonCores=$null;
 install='HOLD';failure=$null;ownerSourcesChanged=$false;userDataTouched=$false;
 fullIntegrationAccepted=$false;E07Accepted=$false;releaseAllowed=$false
}
$out='e06-r13-combined-install-evidence.json'
try {
 $meta=gh api repos/MSSTXNEWS/nox-helion-pp-private-build/actions/artifacts/12783517896 | ConvertFrom-Json
 if($meta.id -ne 12783517896 -or $meta.expired -or
    $meta.workflow_run.id -ne 40611662850 -or
    $meta.workflow_run.head_sha -cne 'e5c50ca6c5db18d75b15c392155b3951a81df6f5') {throw 'E06_PINNED_ARTIFACT_PROVENANCE_HOLD'}
 New-Item -ItemType Directory -Path diagnostic-payload -Force | Out-Null
 gh run download 40611662850 --repo MSSTXNEWS/nox-helion-pp-private-build --name nox-e06-onehost-installer-40611662850 --dir diagnostic-payload
 if($LASTEXITCODE -ne 0){throw 'E06_GITHUB_ARTIFACT_DOWNLOAD_HOLD'}
 $setup=(Resolve-Path 'diagnostic-payload/onehost-candidate/NOX-HELION-V16-DIAGNOSTIC-SETUP.exe').Path
 $receipt.setupActualSha256=(Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash.ToLowerInvariant()
 if($receipt.setupActualSha256 -cne $receipt.setupExpectedSha256){throw 'E06_SETUP_SHA256_HOLD'}
 $root=Join-Path $env:LOCALAPPDATA 'Programs\NOX HELION'
 $stage=$root+'.__p01_stage'
 foreach($path in @($root,$stage,($root+'.__p01_previous'),($root+'.__p01_rollback_saved'))){
   if(Test-Path -LiteralPath $path){throw "E06_INSTALL_PATH_ALREADY_EXISTS_HOLD:$path"}
 }
 $p=Start-Process -FilePath $setup -ArgumentList '/S' -PassThru
 if(!$p.WaitForExit(180000)){
   if(!$p.HasExited){$p.Kill($true)}
   throw 'E06_NSIS_INSTALL_TIMEOUT_HOLD'
 }
 $receipt.setupExitCode=$p.ExitCode
 $receipt.stageExists=Test-Path -LiteralPath $stage
 $receipt.installedMarker=Test-Path -LiteralPath (Join-Path $root 'nox-p01-owned.txt') -PathType Leaf
 $receipt.wpfExecutable=Test-Path -LiteralPath (Join-Path $root 'NOX.P01.Shell.exe') -PathType Leaf
 if($p.ExitCode -ne 0 -or !$receipt.installedMarker -or !$receipt.wpfExecutable){
   # Read-only analysis of the immutable setup. No installed data altered.
   $receipt.rootExists=Test-Path -LiteralPath $root
   $receipt.stageRootExists=Test-Path -LiteralPath $stage
   $receipt.bundledPreflight='NOT_FOUND'
   $receipt.bundledPreflightExitCode=$null
   $receipt.bundledPreflightOutput=$null
   try {
     $sevenZip=Get-Command 7z.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
     if(!$sevenZip){$candidate=Join-Path $env:ProgramFiles '7-Zip\7z.exe';if(Test-Path -LiteralPath $candidate){$sevenZip=Get-Item $candidate}}
     if($sevenZip){
       $destination=Join-Path $env:RUNNER_TEMP 'E06-R13-Frozen-Setup-ReadOnly'
       New-Item -ItemType Directory -Path $destination -Force | Out-Null
       $sevenZipPath=if($sevenZip -is [System.IO.FileInfo]){$sevenZip.FullName}else{$sevenZip.Source}
       & $sevenZipPath x $setup "-o$destination" -y | Out-Null
       if($LASTEXITCODE -eq 0){
         $original=Get-ChildItem -LiteralPath $destination -File -Recurse -Filter 'Preflight-InstallPath.ps1' |
                   Select-Object -First 1
         if($original){
           $receipt.bundledPreflight=(Get-FileHash -LiteralPath $original.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
           $results=@(& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $original.FullName -InstallRoot $root 2>&1)
           $receipt.bundledPreflightExitCode=$LASTEXITCODE
           $receipt.bundledPreflightOutput=($results | Out-String).Substring(0,[Math]::Min(1000,($results | Out-String).Length))
         }
       }
     }
   } catch {
     $receipt.bundledPreflightOutput="FORENSIC_READ_ONLY_ERROR:"+$_.Exception.GetType().Name
   }
   throw "E06_NSIS_INSTALL_HOLD_EXIT_$($p.ExitCode)_STAGE_$($receipt.stageExists)"
 }
 $backend=Join-Path $root 'Backend\NOX_HELION_PRIVATE_CANDIDATE.exe'
 if(!(Test-Path -LiteralPath $backend -PathType Leaf)){throw 'E06_COMBINED_BACKEND_NOT_INSTALLED'}
 $backendItem=Get-Item -LiteralPath $backend -Force
 if(($backendItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){throw 'E06_BACKEND_REPARSE_HOLD'}
 $backendSha=(Get-FileHash -LiteralPath $backend -Algorithm SHA256).Hash.ToLowerInvariant()
 if($backendSha -cne $receipt.backendExpectedSha256){throw 'E06_ORIGINAL_BACKEND_SHA_HOLD'}
 $receipt.originalPythonShaValid=$true
 $stdout=Join-Path $env:RUNNER_TEMP 'E06-R13-Python-Stdout.txt'
 $stderr=Join-Path $env:RUNNER_TEMP 'E06-R13-Python-Stderr.txt'
 $b=Start-Process -FilePath $backend -ArgumentList '--diagnose' -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
 if(!$b.WaitForExit(60000)){
   if(!$b.HasExited){$b.Kill($true)}
   throw 'E06_PYTHON_DIAGNOSE_TIMEOUT_HOLD'
 }
 if($b.ExitCode -ne 0){throw "E06_PYTHON_DIAGNOSE_EXIT_$($b.ExitCode)"}
 $raw=[IO.File]::ReadAllText($stdout)
 if($raw.Length -gt 65536){throw 'E06_PYTHON_DIAGNOSE_OUTPUT_TOO_LARGE'}
 $diag=$raw | ConvertFrom-Json
 if([int]$diag.routes_total -lt 1 -or @($diag.cores).Count -ne 8){throw 'E06_DIAGNOSE_ROUTE_CORE_CONTRACT_HOLD'}
 $receipt.pythonDiagnose='PASS'
 $receipt.pythonRoutes=[int]$diag.routes_total
 $receipt.pythonCores=@($diag.cores).Count
 $receipt.install='COMBINED_DIAGNOSTIC_INSTALL_PASS_NOT_PRODUCT_ACCEPTED'
 Write-Host 'E06_R13_REAL_COMBINED_INSTALL_AND_PYTHON_PROCESS_PASS'
} catch {
 $receipt.failure=$_.Exception.Message
 Write-Warning ("E06_R13_COMBINED_HOLD: "+$receipt.failure)
} finally {
 [IO.File]::WriteAllText((Join-Path (Get-Location) $out),($receipt|ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
 Write-Host ($receipt|ConvertTo-Json -Depth 8)
}
if($receipt.install -cne 'COMBINED_DIAGNOSTIC_INSTALL_PASS_NOT_PRODUCT_ACCEPTED'){throw 'E06_R13_COMBINED_INSTALL_GATE_HOLD'}
