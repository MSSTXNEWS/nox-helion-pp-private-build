# NOX V134 ONEPASS verified reassembly, no deletion/overwrite, no server install.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$Name = 'NOX_HELION_WEB_V29_3_ONEPASS_NATIVE_OWNER_V134.zip'
$ExpectedHash = '2fecf01f47079313c9b097052819574d93d372d7cbfcc4f2d73e5ab82ac4afd4'
$ExpectedBytes = [long]107071440
$Parts = @(
  @{ File = $Name + '.part01'; Bytes = [long]55000000; Sha = 'e7ff916981621443a91b627607b2682de269e04893ba90cd4de3ff2000563a93' },
  @{ File = $Name + '.part02'; Bytes = [long]52071440; Sha = '334a4704aee81db3466ba37239630258832684bb2cca0499837dbc3b81808335' }
)
function Sha([string]$File) { return (Get-FileHash -LiteralPath $File -Algorithm SHA256).Hash.ToLowerInvariant() }
Write-Host 'NOX V134: verify all parts and reconstruct full WEB V29.3 source' -ForegroundColor Cyan
foreach($p in $Parts) {
  $path = Join-Path $PSScriptRoot $p.File
  if(-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw ('HOLD_PART_MISSING ' + $p.File) }
  if((Get-Item -LiteralPath $path).Length -ne $p.Bytes) { throw ('HOLD_PART_SIZE ' + $p.File) }
  if((Sha $path) -cne $p.Sha) { throw ('HOLD_PART_SHA ' + $p.File) }
  Write-Host ('PART_SHA_VERIFIED ' + $p.File)
}
$Target = Join-Path $PSScriptRoot $Name
if(Test-Path -LiteralPath $Target) {
  if((Get-Item -LiteralPath $Target).Length -ne $ExpectedBytes -or (Sha $Target) -cne $ExpectedHash) {
    throw 'HOLD_EXISTING_OUTPUT_SHA_MISMATCH_NO_OVERWRITE'
  }
  Write-Host 'NOX_FULL_SOURCE_ALREADY_VERIFIED' -ForegroundColor Green
  exit 0
}
$Temp = $Target + '.noxpart'
if(Test-Path -LiteralPath $Temp) { throw 'HOLD_EXISTING_PARTIAL_NO_DELETE' }
$targetStream = [IO.File]::Open($Temp,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
try {
  foreach($p in $Parts) {
    $inputPath=Join-Path $PSScriptRoot $p.File
    $inputStream=[IO.File]::OpenRead($inputPath)
    try { $inputStream.CopyTo($targetStream,4194304) } finally { $inputStream.Dispose() }
  }
  $targetStream.Flush($true)
} finally { $targetStream.Dispose() }
if((Get-Item -LiteralPath $Temp).Length -ne $ExpectedBytes -or (Sha $Temp) -cne $ExpectedHash) {
  throw 'HOLD_REASSEMBLED_SHA_NO_SOURCE_DELETION'
}
if(Test-Path -LiteralPath $Target) { throw 'HOLD_CONCURRENT_TARGET_NO_OVERWRITE' }
Move-Item -LiteralPath $Temp -Destination $Target -ErrorAction Stop
Write-Host ('NOX_FULL_WEB_V29_3_SHA_PASS ' + $Target) -ForegroundColor Green
Write-Host 'STAGING ONLY. NOX production, model weights and S03 have not been modified.'
