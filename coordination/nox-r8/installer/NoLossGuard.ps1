# B05 immutable per-user installer verifier; not owner-PC E2E acceptance.
[CmdletBinding()]
param(
 [Parameter(Mandatory)][ValidateSet('PreInstall','PostInstall','PreUninstall')][string]$Mode,
 [Parameter(Mandatory)][string]$InstallDir,
 [Parameter(Mandatory)][string]$ExpectedExeSha,
 [Parameter(Mandatory)][string]$ExpectedReceiptSha,
 [Parameter(Mandatory)][string]$ExpectedSourceSha
)
$ErrorActionPreference='Stop'
function Hold([string]$why) { throw "B05_NOLOSS_HOLD:$why" }
function EqualsCI([string]$a,[string]$b) {
 return [string]::Equals($a,$b,[StringComparison]::OrdinalIgnoreCase)
}
function Check-NoReparse([string]$path) {
 $current=[IO.Path]::GetFullPath($path)
 for($i=0;$i -lt 64;$i++) {
   if(Test-Path -LiteralPath $current) {
     $item=Get-Item -LiteralPath $current -Force
     if(($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){ Hold 'REPARSE_PATH' }
   }
   $parent=[IO.Path]::GetDirectoryName($current.TrimEnd('\'))
   if([string]::IsNullOrEmpty($parent) -or (EqualsCI $parent $current)){ break }
   $current=$parent
 }
}
function Check-Hash([string]$path,[string]$sha) {
 if(-not (Test-Path -LiteralPath $path -PathType Leaf)){ Hold 'FILE_MISSING' }
 Check-NoReparse $path
 if(-not (EqualsCI (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash $sha)){ Hold 'CONTENT_SHA_MISMATCH' }
}
if($ExpectedExeSha -cnotmatch '^[a-fA-F0-9]{64}$'){ Hold 'EXE_SHA_FORMAT' }
if($ExpectedReceiptSha -cnotmatch '^[a-fA-F0-9]{64}$'){ Hold 'RECEIPT_SHA_FORMAT' }
if($ExpectedSourceSha -cnotmatch '^[a-fA-F0-9]{40}$'){ Hold 'SOURCE_SHA_FORMAT' }
if([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)){ Hold 'LOCALAPPDATA_MISSING' }
$base=[IO.Path]::GetFullPath([IO.Path]::Combine($env:LOCALAPPDATA,'Programs','NOX-HELION-R8'))
$expected=[IO.Path]::GetFullPath([IO.Path]::Combine($base,$ExpectedExeSha.ToLowerInvariant()))
$actual=[IO.Path]::GetFullPath($InstallDir)
if(-not (EqualsCI $actual.TrimEnd('\') $expected.TrimEnd('\'))){ Hold 'TARGET_OUTSIDE_IMMUTABLE_PER_USER_ROOT' }
Check-NoReparse $actual
if($Mode -eq 'PreInstall') {
 if(Test-Path -LiteralPath $actual){ Hold 'TARGET_ALREADY_EXISTS' }
 Write-Output 'B05_NOLOSS_PREINSTALL_PASS_RELEASE_HOLD'
 return
}
if(-not (Test-Path -LiteralPath $actual -PathType Container)){ Hold 'TARGET_DIRECTORY_MISSING' }
$allowed=@('NOX.HELION.exe','BUILD_RECEIPT.json')
if($Mode -eq 'PreUninstall'){ $allowed+= 'Uninstall.exe' }
$items=@(Get-ChildItem -LiteralPath $actual -Force)
if($items.Count -ne $allowed.Count){ Hold 'FOREIGN_OR_MISSING_ENTRY' }
foreach($item in $items){
 if($allowed -cnotcontains $item.Name){ Hold 'FOREIGN_ENTRY' }
 if($item.PSIsContainer){ Hold 'UNEXPECTED_DIRECTORY' }
 Check-NoReparse $item.FullName
}
$exe=[IO.Path]::Combine($actual,'NOX.HELION.exe')
$receiptPath=[IO.Path]::Combine($actual,'BUILD_RECEIPT.json')
Check-Hash $exe $ExpectedExeSha
Check-Hash $receiptPath $ExpectedReceiptSha
$receipt=Get-Content -LiteralPath $receiptPath -Encoding UTF8 -Raw | ConvertFrom-Json
if(-not (EqualsCI ([string]$receipt.source_git_sha) $ExpectedSourceSha)){ Hold 'RECEIPT_WRONG_SOURCE' }
if(-not (EqualsCI ([string]$receipt.exe_sha256) $ExpectedExeSha)){ Hold 'RECEIPT_WRONG_EXE' }
if([string]$receipt.schema -cne 'NOX_R8_NATIVE_SINGLE_EXE_V1'){ Hold 'RECEIPT_WRONG_SCHEMA' }
Write-Output ("B05_NOLOSS_{0}_PASS_RELEASE_HOLD" -f $Mode.ToUpperInvariant())
