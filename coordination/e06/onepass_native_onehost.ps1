# NOX T06 · one manual native candidate from the existing owner artifacts.
# Reuses canonical stage_p01.py, WPF/WebView2, P02 pipe and NSIS. No new host.
[CmdletBinding()]
param(
 [Parameter(Mandatory=$true)][string]$PythonExe,
 [Parameter(Mandatory=$true)][string]$PythonNativeSmokeReceipt,
 [Parameter(Mandatory=$true)][string]$OutputRoot,
 [Parameter(Mandatory=$true)][string]$RunId,
 [string]$CreativeSourceRoot='',
 [string]$WowSourceRoot='',
 [string]$PersonaBundlePath=''
)
$ErrorActionPreference='Stop';Set-StrictMode -Version Latest
if ($RunId -cnotmatch '\A[A-Za-z0-9][A-Za-z0-9._:-]{1,127}\z') { throw 'T06_INVALID_RUN_ID' }
$repo=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
$stage=Join-Path $repo 'work/e06/staged/R11'
$py=Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -First 1
if(!$py -or (Test-Path -LiteralPath $stage)) { throw 'T06_STAGE_NOT_EMPTY_OR_PYTHON_MISSING' }
& $py.Source (Join-Path $PSScriptRoot 'stage_p01.py')
if($LASTEXITCODE -ne 0) { throw 'T06_SOURCELOCK_DONOR_STAGE_FAILED' }
$args=@{SourceRoot=$stage;PythonExe=$PythonExe;
        PythonNativeSmokeReceipt=$PythonNativeSmokeReceipt;
        OutputRoot=$OutputRoot;RunId=$RunId}
if($CreativeSourceRoot) {$args.CreativeSourceRoot=$CreativeSourceRoot}
if($WowSourceRoot) {$args.WowSourceRoot=$WowSourceRoot}
if($PersonaBundlePath) {$args.PersonaBundlePath=$PersonaBundlePath}
& (Join-Path $PSScriptRoot 'build_onehost_installer.ps1') @args
if(!(Test-Path -LiteralPath (Join-Path $OutputRoot 'ONEHOST_DIAGNOSTIC_RECEIPT.json') -PathType Leaf)){
 throw 'T06_NSIS_ONEHOST_RECEIPT_MISSING'
}
Write-Host 'T06_NATIVE_ONEHOST_CANDIDATE_NOT_E07_ACCEPTED'
