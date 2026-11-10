# NOX V16 E07 C2 / real PowerShell native no-clobber concurrency regression.
# This evaluates the ACTUAL production function AST, not a copied implementation.
[CmdletBinding()]
param([string]$OwnerScript='coordination/e06/Emit-E07ImmutableHandoff.ps1')
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$tokens=$null; $parseErrors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile(
  (Resolve-Path -LiteralPath $OwnerScript).Path,[ref]$tokens,[ref]$parseErrors)
if ($null -ne $parseErrors -and $parseErrors.Count -gt 0) {
 throw 'E07_NO_CLOBBER_OWNER_AST_INVALID'
}
$functions=@($ast.FindAll({
 param($node)
 $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
 $node.Name -ceq 'WriteReceiptNoClobber'
},$true))
if ($functions.Count -ne 1) { throw 'E07_NO_CLOBBER_WRITER_MISSING_OR_DUPLICATED' }
$writerText=$functions[0].Extent.Text
if (!$writerText.Contains('[IO.FileMode]::CreateNew') -or
    !$writerText.Contains('[IO.FileShare]::None') -or
    !$writerText.Contains('$stream.Flush($true)')) {
 throw 'E07_NO_CLOBBER_EXCLUSIVE_WRITER_CONTRACT_HOLD'
}
Invoke-Expression $writerText
$dir=Join-Path ([IO.Path]::GetTempPath()) ('nox-e07-race-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $dir -ErrorAction Stop | Out-Null
$jobs=@()
try {
 $target=Join-Path $dir 'receipt.json'
 $sentinel='{"existing":"DO_NOT_REPLACE"}'
 [IO.File]::WriteAllText($target,$sentinel)
 $rejected=$false
 try { WriteReceiptNoClobber $target '{"new":true}' }
 catch {
  $ex=$_.Exception
  if ($ex -is [IO.IOException] -or $ex.InnerException -is [IO.IOException]) {
    $rejected=$true
  } else { throw }
 }
 if (!$rejected -or [IO.File]::ReadAllText($target) -cne $sentinel) {
  throw 'E07_NO_CLOBBER_EXISTING_FILE_OVERWRITTEN'
 }
 Remove-Item -LiteralPath $target -Force -ErrorAction Stop
 Import-Module ThreadJob -ErrorAction Stop
 $payload='{"schema":"NOX_V16_E07_IMMUTABLE_HANDOFF_V1","release_accepted":false}'
 for ($i=0;$i -lt 8;$i++) {
  $jobs+=Start-ThreadJob -ThrottleLimit 8 -ArgumentList $writerText,$target,$payload -ScriptBlock {
   param($source,$file,$text)
   Invoke-Expression $source
   try {
    WriteReceiptNoClobber $file $text
    'CREATED'
   } catch {
    $ex=$_.Exception
    if ($ex -is [IO.IOException] -or $ex.InnerException -is [IO.IOException]) {
      'COLLISION'
    } else { throw }
   }
  }
 }
 $jobs | Wait-Job | Out-Null
 $out=@($jobs | Receive-Job -ErrorAction Stop)
 if (@($out | Where-Object { $_ -ceq 'CREATED' }).Count -ne 1 -or
     @($out | Where-Object { $_ -ceq 'COLLISION' }).Count -ne 7 -or
     [IO.File]::ReadAllText($target) -cne $payload) {
   throw "E07_NO_CLOBBER_CONCURRENT_WRITERS_FAILED:$($out -join ',')"
 }
 Write-Host 'E07_NO_CLOBBER_1_OF_8_NATIVE_PASS_RELEASE_NOT_ACCEPTED'
} finally {
 foreach ($job in $jobs) { Remove-Job -Job $job -Force -ErrorAction SilentlyContinue }
 Remove-Item -LiteralPath $dir -Recurse -Force -ErrorAction SilentlyContinue
}
