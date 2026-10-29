# Windows PowerShell 5.1 SOURCE-ONLY guard test; no installer/uninstall execution.
param([Parameter(Mandatory=$true)][string]$VerifyScript,
      [Parameter(Mandatory=$true)][string]$RemoveScript)
$ErrorActionPreference = 'Stop'
$cases = @(
  @{ Json='{"schema":"NOX_P01_PAYLOAD_SHA256_V1","files":[{"path":"a","sha256":"ok"}]}'; Reject=$false },
  @{ Json='{"schema":"bad","schema":"NOX_P01_PAYLOAD_SHA256_V1"}'; Reject=$true },
  @{ Json='{"schema":"x","SCHEMA":"y"}'; Reject=$true },
  @{ Json='{"files":[{"path":"x","path":"y"}]}'; Reject=$true },
  @{ Json='{"files":[{"path":"x"},{"path":"y"}]}'; Reject=$false },
  @{ Json='{"sc\u0068ema":"alias"}'; Reject=$true },
  @{ Json='{"value":"comma , colon : braces { } and escaped \" quote"}'; Reject=$false }
)
$count = 0
foreach ($source in @($VerifyScript,$RemoveScript)) {
  $tokens = $null; $parseErrors = $null
  $ast = [System.Management.Automation.Language.Parser]::ParseFile(
    (Resolve-Path -LiteralPath $source).Path,[ref]$tokens,[ref]$parseErrors)
  if (@($parseErrors).Count -gt 0) { throw "PS syntax invalid: $source" }
  $fn = $ast.Find({
    param($n)
    $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
      $n.Name -eq 'Assert-NoDuplicateJsonMembers'
  },$true)
  if ($null -eq $fn) { throw "Guard missing: $source" }
  & {
    param($body,$vectors)
    . ([scriptblock]::Create($body))
    foreach ($v in $vectors) {
      $failed=$false
      try { Assert-NoDuplicateJsonMembers $v.Json } catch { $failed=$true }
      if ($failed -ne $v.Reject) { throw "Unexpected guard result $($v.Json)" }
    }
  } $fn.Extent.Text $cases
  $count += $cases.Count
}
"P01_DUPKEY_NEGATIVE_GUARD_PASS=$count"
