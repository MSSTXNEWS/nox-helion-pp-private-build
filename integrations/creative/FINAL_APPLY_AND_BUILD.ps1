# NOX HELION · FINAL CREATIVE INTEGRATION PATCH · requires Windows 10/11 x64
# REQUIRES already VERIFIED and DISPOSABLE R13 staged R11 tree, original Python diagnostic EXE,
# approved E06/R13 build script and installed .NET 8 / Python 3.12 / NSIS.
# Does NOT overwrite source or install on user's machine; creates independent candidate.
[CmdletBinding()]
param(
 [Parameter(Mandatory=$true)][string]$VerifiedR13StagedR11,
 [Parameter(Mandatory=$true)][string]$OriginalR13Builder,
 [Parameter(Mandatory=$true)][string]$OriginalPythonExe,
 [Parameter(Mandatory=$true)][string]$Wow200SourceRoot,
 [Parameter(Mandatory=$true)][string]$OutputRoot,
 [Parameter()][string]$PersonaBundlePath = ''
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$patchRoot=(Resolve-Path -LiteralPath $PSScriptRoot).Path
$old=(Resolve-Path -LiteralPath $VerifiedR13StagedR11).Path
$builder=(Resolve-Path -LiteralPath $OriginalR13Builder).Path
$original=(Resolve-Path -LiteralPath $OriginalPythonExe).Path
$wow=(Resolve-Path -LiteralPath $Wow200SourceRoot).Path
if (Test-Path -LiteralPath $OutputRoot){ throw 'NO_LOSS_HOLD: output exists; choose a new folder' }
$expectedPython='4e488372cf3f6410d268a7ef72b3e4b359a7a3e6642c7a16ac2e6f7eb06fc5f3'
if((Get-FileHash -LiteralPath $original -Algorithm SHA256).Hash.ToLowerInvariant() -cne $expectedPython){throw 'NO_LOSS_HOLD: source Python EXE does not match R13'}
$art=@{
 'home.png'='382c1069afcaaaed11c319796f2c553d2bd977d7e46c68ecd7d55af26e132a4a'
 'menu.png'='4c73d137e6d25f496abb006dbb8af08b1fe272d2f935c5006f0f42b6fd9992b9'
 'core01.png'='343e5c73539358fe2c086706b4155cc0f9cd9702fcd40a98b4aab130585bec97'
 'menu_sections.png'='7d181604f913cf9956c173c14da3dc7fd0238c389322896588cec4407b4024a4'
}
foreach($name in $art.Keys){
 $f=Join-Path $old ('Assets/'+$name)
 if(!(Test-Path -LiteralPath $f -PathType Leaf) -or (Get-FileHash -LiteralPath $f -Algorithm SHA256).Hash.ToLowerInvariant() -cne $art[$name]){throw ('NO_LOSS_HOLD: approved D02 SHA mismatch '+$name)}
}
$py=Get-Command py.exe -ErrorAction Stop
& $py.Source -3.12 -c 'import sys; assert sys.version_info[:2]==(3,12)'
if($LASTEXITCODE -ne 0){throw 'Python 3.12 required'}
New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
$workspace=(Resolve-Path -LiteralPath $OutputRoot).Path
$stage=Join-Path $workspace 'R11'
Copy-Item -LiteralPath $old -Destination $stage -Recurse
$workerRoot=Join-Path $workspace 'creative-worker'
New-Item -ItemType Directory -Path $workerRoot -Force | Out-Null
# Python packages installed only to isolated per-build venv, never to user's global interpreter.
& $py.Source -3.12 -m venv (Join-Path $workerRoot '.venv')
if($LASTEXITCODE -ne 0){throw 'CREATIVE_VENV_FAILED'}
$python=Join-Path $workerRoot '.venv/Scripts/python.exe'
& $python -m pip install --disable-pip-version-check 'pyinstaller==6.16.0' 'huggingface_hub==0.36.0' 'trimesh==4.8.2' 'numpy==2.3.4'
if($LASTEXITCODE -ne 0){throw 'CREATIVE_DEPENDENCY_INSTALL_FAILED'}
$env:PYTHONPATH=$patchRoot
& $python -m unittest discover -s (Join-Path $patchRoot 'tests') -v
if($LASTEXITCODE -ne 0){throw 'CREATIVE_PROTOCOL_TEST_HOLD'}
& $python -m PyInstaller --noconfirm --clean --onedir --console --name NOX_CreativeWorker --paths $patchRoot --collect-all huggingface_hub --collect-all trimesh --distpath (Join-Path $workerRoot 'dist') --workpath (Join-Path $workerRoot 'build') (Join-Path $patchRoot 'creative_worker.py')
if($LASTEXITCODE -ne 0){throw 'CREATIVE_WORKER_COMPILE_HOLD'}
& $python (Join-Path $patchRoot 'stage_creative.py') $stage $patchRoot
if($LASTEXITCODE -ne 0){throw 'CREATIVE_STAGE_HOLD'}
& $python -m unittest discover -s (Join-Path $wow 'tests') -v
if($LASTEXITCODE -ne 0){throw 'WOW200_SHA_GATES_TEST_HOLD'}
& $python (Join-Path $wow 'stage_wow200.py') $stage $wow
if($LASTEXITCODE -ne 0){throw 'WOW200_STAGE_HOLD'}
if(-not [string]::IsNullOrWhiteSpace($PersonaBundlePath)){
  $personaArchive=(Resolve-Path -LiteralPath $PersonaBundlePath -ErrorAction Stop).Path
  $personaSha='9abc124ce1a543417afcd2a08097c5d72b5901a10830869cf495fa7045330ec7'
  if((Get-FileHash -LiteralPath $personaArchive -Algorithm SHA256).Hash.ToLowerInvariant() -cne $personaSha){throw 'PERSONA_R15_SOURCE_SHA_HOLD'}
  & $python (Join-Path $patchRoot 'stage_persona_media.py') $stage $personaArchive
  if($LASTEXITCODE -ne 0){throw 'PERSONA_R15_STAGE_HOLD'}
  if(!(Test-Path -LiteralPath (Join-Path $workspace 'PERSONA_STAGE_RECEIPT.json') -PathType Leaf)){throw 'PERSONA_R15_RECEIPT_HOLD'}
}else{Write-Warning 'PERSONA_R15_NOT_BUNDLED: supply -PersonaBundlePath to include four owner-source loops; EV stays identity HOLD'}
if($LASTEXITCODE -ne 0){throw 'WOW200_STAGE_HOLD'}
$builderCopy=Join-Path $workspace 'build_onehost_installer.ps1'
Copy-Item -LiteralPath $builder -Destination $builderCopy
$workerDist=Join-Path $workerRoot 'dist/NOX_CreativeWorker'
& $python (Join-Path $patchRoot 'patch_installer.py') $builderCopy $workerDist
if($LASTEXITCODE -ne 0){throw 'CREATIVE_INSTALLER_PATCH_HOLD'}
# Work from the original owner E06 builder, which preserves original verified NSIS logic.
# The original R13 builder may depend on an Installer folder; it is copied untouched in R11.
& $builderCopy -SourceRoot $stage -PythonExe $original -OutputRoot (Join-Path $workspace 'candidate') -RunId 'NOX-V16-CREATIVE-FINAL-EXPLICIT-LOCAL'
if($LASTEXITCODE -ne 0){throw 'CREATIVE_WINDOWS_NSIS_HOLD'}
$setup=Join-Path $workspace 'candidate/NOX-HELION-V16-DIAGNOSTIC-SETUP.exe'
if(!(Test-Path $setup -PathType Leaf)){throw 'CREATIVE_NSIS_SETUP_MISSING'}
$receipt=[ordered]@{status='WINDOWS_CANDIDATE_BUILT_NOT_E07_ACCEPTED';setup_sha256=(Get-FileHash $setup -Algorithm SHA256).Hash.ToLowerInvariant();setup_bytes=(Get-Item $setup).Length;original_d02_sha256=$art;original_r13_python_sha256=$expectedPython;wow200_stage_receipt=(Join-Path $workspace 'WOW200_STAGE_RECEIPT.json');created_utc=(Get-Date).ToUniversalTime().ToString('o');e07_accepted=$false}
$receipt | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $workspace 'CREATIVE_FINAL_BUILD_RECEIPT.json') -Encoding utf8
Write-Host "WINDOWS_CANDIDATE_CREATED_NOT_E07_ACCEPTED $($receipt.setup_sha256)"