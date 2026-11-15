# NOX V133 ONEPASS verified reassembly, no deletion/overwrite, no server install.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$Name = 'NOX_HELION_WEB_V29_3_CONVERGED_FULL_ONEPASS.zip'
$ExpectedHash = '2ac6be7b5f84e77f35f9b8b1dbfb25cab72e197f0d9f0aad70b886166a296bc4'
$ExpectedBytes = [long]106992154
$Parts = @(
  @{ File = $Name + '.part01'; Bytes = [long]55000000; Sha = '47011d0ee62c299dbd7388101185862d523c746c6b71438bf3b00517c2c76847' },
  @{ File = $Name + '.part02'; Bytes = [long]51992154; Sha = 'e906e8b66aef160f04652322e0d6805625c2c27555bc074c0e38308d58a7e9b0' }
)
function Sha([string]$File) { return (Get-FileHash -LiteralPath $File -Algorithm SHA256).Hash.ToLowerInvariant() }
Write-Host 'NOX V133: verify all parts and reconstruct full WEB V29.3 source' -ForegroundColor Cyan
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
