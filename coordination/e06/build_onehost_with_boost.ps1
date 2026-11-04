# NOX EXPRESS Windows x64: authenticated V4 cache -> ONE existing E06 owner builder.
# Diagnostic source build only. Never install a model or claim E07/RELEASE.
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

function Assert-BoostPlainParent {
 param([Parameter(Mandatory=$true)][string]$Candidate)
 $cursor=Split-Path -Parent ([IO.Path]::GetFullPath($Candidate))
 while (-not [string]::IsNullOrWhiteSpace($cursor)) {
   $node=Get-Item -LiteralPath $cursor -Force -ErrorAction Stop
   if (($node.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
     throw 'BOOST_PARENT_REPARSE_HOLD'
   }
   $higher=Split-Path -Parent $cursor
   if ([string]::IsNullOrWhiteSpace($higher) -or $higher -ceq $cursor) { break }
   $cursor=$higher
 }
}

$repo=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
$python=Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -First 1
if (!$python) { throw 'BOOST_PYTHON_REQUIRED' }
$pythonVersion=(& $python.Source -c "import sys;print('.'.join(str(v) for v in sys.version_info[:3]))" | Out-String).Trim()
if ($LASTEXITCODE -ne 0 -or $pythonVersion -cne '3.12.10') {
 throw 'BOOST_WINDOWS_PYTHON_31210_REQUIRED'
}
if (!(Test-Path -LiteralPath $BoostCacheZip -PathType Leaf)) { throw 'BOOST_ARCHIVE_REQUIRED' }
if (!(Test-Path -LiteralPath $SourceRoot -PathType Container)) { throw 'BOOST_DISPOSABLE_SOURCE_REQUIRED' }
$outFull=[IO.Path]::GetFullPath($OutputRoot)
$sourceFull=[IO.Path]::GetFullPath($SourceRoot).TrimEnd([char[]]@('\','/'))
if ($outFull -ceq $sourceFull -or
    $outFull.StartsWith(($sourceFull+[IO.Path]::DirectorySeparatorChar),
                         [StringComparison]::OrdinalIgnoreCase)) {
 throw 'BOOST_SOURCE_OUTPUT_OVERLAP_HOLD'
}
Assert-BoostPlainParent -Candidate $outFull
if (Test-Path -LiteralPath $outFull) { throw 'BOOST_OWNER_OUTPUT_EXISTS_NO_OVERWRITE' }
# The ORIGINAL E06 owner requires OutputRoot NOT TO EXIST until its own publish.
# The previous wrapper placed boost-v4-staged INSIDE OutputRoot and then made
# the owner fail unconditionally with OUTPUT_ALREADY_EXISTS_NO_OVERWRITE.
$stageRoot=$outFull + '.boost-v4-staged'
Assert-BoostPlainParent -Candidate $stageRoot
if (Test-Path -LiteralPath $stageRoot) { throw 'BOOST_STAGE_OUTPUT_COLLISION_HOLD' }
& $python.Source (Join-Path $repo 'coordination/e06/boost_v4_stage.py') --archive $BoostCacheZip --out $stageRoot
if ($LASTEXITCODE -ne 0) { throw 'BOOST_PHYSICAL_STAGE_HOLD' }

$receipt=Join-Path $stageRoot 'BOOST_STAGE_RECEIPT.json'
if (!(Test-Path -LiteralPath $receipt -PathType Leaf)) { throw 'BOOST_RECEIPT_MISSING_HOLD' }
$proof=Get-Content -LiteralPath $receipt -Raw -Encoding UTF8 | ConvertFrom-Json
if ($proof.schema -cne 'NOX-BOOST-V4-STAGE-V1' -or
    (@('2ca2647e46edd1e110db1569cb6a636ceee8e8154b416560ad43a87fb95545bd','26d2ed7ca66aaa0ce4d2b695537484f51c2080140f79cc576501f211c2190938') -cnotcontains ([string]$proof.archive_sha256)) -or
    $proof.stage_only -ne $true -or $proof.owner_source_mutated -ne $false -or
    $proof.onehost_executed -ne $false -or $proof.e07_pass -ne $false) {
 throw 'BOOST_SOURCE_STAGE_RECEIPT_HOLD'
}
$files=@($proof.files)
if ($files.Count -lt 20) { throw 'BOOST_STAGE_MANIFEST_INCOMPLETE' }
$seen=@{}
$d02Count=0
$nugetCount=0
foreach ($entry in $files) {
 $relative=[string]$entry.path
 $segments=@($relative.Split('/'))
 if ([string]::IsNullOrWhiteSpace($relative) -or
     $relative.Contains('\') -or $relative.Contains(':') -or
     $relative.StartsWith('/') -or $segments.Count -lt 2 -or
     ($segments -contains '') -or ($segments -contains '.') -or
     ($segments -contains '..') -or $seen.ContainsKey($relative) -or
     @('approved-d02','nuget-feed','fluent') -cnotcontains $segments[0]) {
   throw 'BOOST_STAGE_RELATIVE_PATH_HOLD'
 }
 $seen[$relative]=$true
 if ($segments[0] -ceq 'approved-d02') { $d02Count++ }
 if ($segments[0] -ceq 'nuget-feed') { $nugetCount++ }
 $local=Join-Path $stageRoot ($relative.Replace('/',[IO.Path]::DirectorySeparatorChar))
 $item=Get-Item -LiteralPath $local -Force -ErrorAction Stop
 if ($item -isnot [IO.FileInfo] -or
     ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
     [string]$entry.sha256 -cnotmatch '\A[0-9a-f]{64}\z' -or
     $item.Length -ne [long]$entry.bytes -or
     (Get-FileHash -LiteralPath $local -Algorithm SHA256).Hash.ToLowerInvariant() -cne
       ([string]$entry.sha256).ToLowerInvariant()) {
   throw 'BOOST_STAGE_PHYSICAL_SHA_HOLD'
 }
}
if ($d02Count -ne 4 -or $nugetCount -ne 16) {
 throw 'BOOST_STAGE_APPROVED_D02_OR_NUGET_COUNT_HOLD'
}
$feed=Join-Path $stageRoot 'nuget-feed'
if (!(Test-Path -LiteralPath $feed -PathType Container)) { throw 'BOOST_NUGET_FEED_MISSING' }

# Reuse already-approved local .nupkg feed in the ORIGINAL dotnet publish.
# Additive only: NuGet's existing sources/permissions remain unchanged.
# Never invoke a second WPF renderer, installer, backend or model downloader.
$argsOwner=@{
 SourceRoot=$SourceRoot;PythonExe=$PythonExe;OutputRoot=$outFull;RunId=$RunId;
 CreativeSourceRoot=(Join-Path $repo 'integrations/creative');
 WowSourceRoot=(Join-Path $repo 'integrations/wow200')
}
if ($PythonNativeSmokeReceipt) { $argsOwner.PythonNativeSmokeReceipt=$PythonNativeSmokeReceipt }
$priorSources=[Environment]::GetEnvironmentVariable('RestoreAdditionalProjectSources','Process')
try {
 $additional=$feed
 if (-not [string]::IsNullOrWhiteSpace($priorSources)) { $additional+=';'+$priorSources }
 [Environment]::SetEnvironmentVariable('RestoreAdditionalProjectSources',$additional,'Process')
 & (Join-Path $repo 'coordination/e06/build_onehost_installer.ps1') @argsOwner
 if ($LASTEXITCODE -ne 0) { throw 'BOOST_OWNER_BUILD_FAILED' }
} finally {
 [Environment]::SetEnvironmentVariable('RestoreAdditionalProjectSources',$priorSources,'Process')
}
# Admit only a real existing owner's diagnostic candidate; no E07 promotion.
$built=Join-Path $outFull 'ONEHOST_DIAGNOSTIC_RECEIPT.json'
$setup=Join-Path $outFull 'NOX-HELION-V16-DIAGNOSTIC-SETUP.exe'
if (!(Test-Path -LiteralPath $built -PathType Leaf) -or
    !(Test-Path -LiteralPath $setup -PathType Leaf)) {
 throw 'BOOST_OWNER_DIAGNOSTIC_CANDIDATE_MISSING'
}
$result=Get-Content -LiteralPath $built -Raw -Encoding UTF8 | ConvertFrom-Json
$head=((& git -C $repo rev-parse HEAD) | Out-String).Trim().ToLowerInvariant()
if ($LASTEXITCODE -ne 0 -or
    $result.schema -cne 'NOX-E06-ONEHOST-DIAGNOSTIC-NSIS-v1' -or
    $result.source_commit_sha1 -cne $head -or
    $result.release_accepted -ne $false -or
    $result.installer_lifecycle_tested -ne $false -or
    [string]$result.installer_sha256 -cnotmatch '\A[0-9a-f]{64}\z' -or
    [long]$result.installer_bytes -ne (Get-Item -LiteralPath $setup).Length -or
    (Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash.ToLowerInvariant() -cne
      ([string]$result.installer_sha256).ToLowerInvariant()) {
 throw 'BOOST_OWNER_DIAGNOSTIC_BYTES_OR_HEAD_HOLD'
}
Write-Host ("BOOST_V4_OWNER_SETUP_BUILT_NOT_E07_ACCEPTED setup_sha256="+$result.installer_sha256+
            " source_sha="+$head+" receipt="+$built)
