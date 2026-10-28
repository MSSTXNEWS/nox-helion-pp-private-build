# E06 R13. Disposable Windows runner ONLY. Never run on an end-user host.
[CmdletBinding()]
param([int]$PollSeconds = 120)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($env:RUNNER_OS -cne 'Windows' -or $env:CI -cne 'true') {
  throw 'E06_CI_ONLY_NO_USER_MACHINE_MUTATION'
}
$RunId = "E06-R13-$env:GITHUB_RUN_ID"
$out = Join-Path (Get-Location) 'e06-r13-webview2-evidence.json'
$guid = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
$keys = @(
  "Registry::HKEY_CURRENT_USER\Software\Microsoft\EdgeUpdate\Clients\$guid",
  "Registry::HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\$guid",
  "Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\EdgeUpdate\Clients\$guid"
)
function Get-RegisteredRuntime {
  foreach ($key in $keys) {
    try {
      $v = [string](Get-ItemProperty -LiteralPath $key -ErrorAction Stop).pv
      $parsed = [version]$v
      if ($parsed.Major -gt 0) {return [ordered]@{key=$key;version=$v}}
    } catch {}
  }
  return $null
}
$receipt = [ordered]@{
  schema='NOX_E06_R13_WEBVIEW2_CI_PREREQ_V1';runId=$RunId;
  githubSha=$env:GITHUB_SHA;sourceMain='eb46b49fb8a022cefa679afb8606877016808db1';
  ciOnly=$true;originalSourcesModified=$false;installerSourceModified=$false;
  url='https://go.microsoft.com/fwlink/p/?LinkId=2124701';
  before=$null;after=$null;installerSha256=$null;
  signature=$null;exitCode=$null;elapsedSeconds=$null;
  gate='HOLD';failure=$null;releaseAccepted=$false
}
try {
  $receipt.before=Get-RegisteredRuntime
  if ($null -eq $receipt.before) {
    $dest=Join-Path $env:RUNNER_TEMP 'E06-WebView2-EvergreenStandaloneX64.exe'
    Invoke-WebRequest -Uri $receipt.url -OutFile $dest -MaximumRedirection 8 -TimeoutSec 900
    if (!(Test-Path -LiteralPath $dest -PathType Leaf) -or
        (Get-Item -LiteralPath $dest).Length -lt 1000000) {
      throw 'E06_OFFICIAL_STANDALONE_MISSING_OR_UNEXPECTED_SIZE'
    }
    $item=Get-Item -LiteralPath $dest -Force
    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {throw 'E06_STANDALONE_REPARSE_HOLD'}
    $receipt.installerSha256=(Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash.ToLowerInvariant()
    $sign=Get-AuthenticodeSignature -FilePath $dest
    $receipt.signature=[string]$sign.Status
    if ($sign.Status -ne 'Valid' -or
        $sign.SignerCertificate.Subject -notmatch 'Microsoft Corporation') {
      throw 'E06_STANDALONE_MICROSOFT_SIGNATURE_HOLD'
    }
    $start=[DateTime]::UtcNow
    $p=Start-Process -FilePath $dest -ArgumentList @('/silent','/install') -Wait -PassThru
    $receipt.exitCode=$p.ExitCode
    if ($p.ExitCode -notin @(0,1638,3010)) {throw "E06_STANDALONE_INSTALL_EXIT_$($p.ExitCode)"}
    $receipt.elapsedSeconds=[math]::Round(([DateTime]::UtcNow-$start).TotalSeconds,1)
    $attempts=[math]::Max(1,[int][math]::Ceiling($PollSeconds/5))
    for ($i=0;$i -lt $attempts;$i++) {
      $receipt.after=Get-RegisteredRuntime
      if ($null -ne $receipt.after) {break}
      Start-Sleep -Seconds 5
    }
  } else {
    $receipt.after=$receipt.before
  }
  if ($null -eq $receipt.after) {throw 'E06_STANDALONE_NOT_REGISTERED_HOLD'}
  $receipt.gate='REGISTERED_RUNTIME_PASS_NOT_PRODUCT_ACCEPTANCE'
  Write-Host "E06_R13_WEBVIEW2_REGISTERED_PASS version=$($receipt.after.version)"
} catch {
  $receipt.failure=$_.Exception.Message
  Write-Warning "E06_R13_WEBVIEW2_HOLD $($receipt.failure)"
} finally {
  [IO.File]::WriteAllText($out,($receipt|ConvertTo-Json -Depth 8),[Text.UTF8Encoding]::new($false))
  Write-Host ($receipt|ConvertTo-Json -Depth 8)
}
if ($receipt.gate -cne 'REGISTERED_RUNTIME_PASS_NOT_PRODUCT_ACCEPTANCE') {
  throw 'E06_WEBVIEW2_PREREQ_GATE_HOLD'
}
