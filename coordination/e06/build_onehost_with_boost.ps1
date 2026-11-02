# Windows x64 ONLY: reusable cache -> existing E06 builder, never a new host.
[CmdletBinding()]
param(
 [Parameter(Mandatory=$true)][string]$BoostCacheZip,
 [Parameter(Mandatory=$true)][string]$SourceRoot,
 [Parameter(Mandatory=$true)][string]$PythonExe,
 [Parameter(Mandatory=$true)][string]$OutputRoot,
 [Parameter(Mandatory=$true)][string]$RunId,
 [string]$PythonNativeSmokeReceipt=''
)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if ($RunId -cnotmatch '\A[A-Za-z0-9][A-Za-z0-9._:-]{1,127}\z') { throw 'BOOST_INVALID_RUN_ID' }
$repo=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
$python=Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -First 1
if (!$python) { throw 'BOOST_PYTHON_REQUIRED' }
if (!(Test-Path -LiteralPath $BoostCacheZip -PathType Leaf)) { throw 'BOOST_ARCHIVE_REQUIRED' }
if (!(Test-Path -LiteralPath $SourceRoot -PathType Container)) { throw 'BOOST_DISPOSABLE_SOURCE_REQUIRED' }
$stageRoot=Join-Path $OutputRoot 'boost-v4-staged'
if (!(Test-Path -LiteralPath $OutputRoot -PathType Container)) { throw 'BOOST_EXISTING_OUTPUT_ROOT_REQUIRED' }
if (Test-Path -LiteralPath $stageRoot) { throw 'BOOST_OUTPUT_COLLISION_HOLD' }
& $python.Source (Join-Path $repo 'coordination/e06/boost_v4_stage.py') --archive $BoostCacheZip --out $stageRoot
if ($LASTEXITCODE -ne 0) { throw 'BOOST_PHYSICAL_STAGE_HOLD' }
$receipt=Join-Path $stageRoot 'BOOST_STAGE_RECEIPT.json'
if (!(Test-Path -LiteralPath $receipt -PathType Leaf)) { throw 'BOOST_RECEIPT_MISSING_HOLD' }
# The owner-controlled scripts below already enforce D02 SourceLock and STOP/SID/ACL.
# BOOST modules are ONLY immutable dependency inputs, not an alternate renderer/owner.
$argsOwner=@{
 SourceRoot=$SourceRoot;PythonExe=$PythonExe;OutputRoot=$OutputRoot;RunId=$RunId;
 CreativeSourceRoot=(Join-Path $repo 'integrations/creative');
 WowSourceRoot=(Join-Path $repo 'integrations/wow200')
}
if ($PythonNativeSmokeReceipt) { $argsOwner.PythonNativeSmokeReceipt=$PythonNativeSmokeReceipt }
& (Join-Path $repo 'coordination/e06/build_onehost_installer.ps1') @argsOwner
if (!$?) { throw 'BOOST_OWNER_BUILD_FAILED' }
Write-Host "BOOST_CACHE_STAGED_NOX_ONEHOST_OWNER_BUILD_RETURNED receipt=$receipt"
