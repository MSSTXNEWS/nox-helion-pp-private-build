# NOX P01 C11: disposable Windows-only native negative cases.
[CmdletBinding()]
param()
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if ($env:OS -ne 'Windows_NT' -or $env:CI -cne 'true') { throw 'P01_C11_WINDOWS_CI_ONLY' }
$project = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\C09'))
$builder=Join-Path $project 'Installer\Build-NSIS.ps1'
$verifier=Join-Path $project 'Installer\Verify-Payload.ps1'
$prereq=Join-Path $project 'Installer\Get-P01Prerequisites.ps1'
$temp=Join-Path $env:RUNNER_TEMP ('NOX_P01_C11_'+[guid]::NewGuid().ToString('N'))
$root=Join-Path $temp 'payload'
[void](New-Item -ItemType Directory -Path $root -Force)
$count=0
function Must([bool]$Condition,[string]$Message) { if (-not $Condition) { throw "P01_C11_ASSERT:$Message" } }
function ScriptCase([string]$Path,[string[]]$Arguments,[bool]$Expected,[string]$ErrorToken) {
  $oldPreference=$ErrorActionPreference
  $ErrorActionPreference='Continue'
  try {
    $output=& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $Path @Arguments 2>&1
    $status=$LASTEXITCODE
  } finally { $ErrorActionPreference=$oldPreference }
  if ($Expected) { Must ($status -eq 0) "expected success: $Path status=$status $output" }
  else { Must ($status -ne 0) "expected rejected: $Path" ; Must ((($output | Out-String).Contains($ErrorToken))) "wrong error: expected=$ErrorToken actual=$output" }
}
function ManifestToDisk([object]$Value,[string]$Path) {
  [IO.File]::WriteAllText($Path,($Value | ConvertTo-Json -Depth 7),(New-Object System.Text.UTF8Encoding($false)))
}
try {
  $projectRoot=Join-Path $temp 'missing-source'
  ScriptCase $builder @('-SourceRoot',$projectRoot,'-OutputDir',(Join-Path $temp 'out'),'-RunId','P01-UNSET') $false 'P01_BUILD_INVALID_RUN_ID'
  $count++
  ScriptCase $builder @('-SourceRoot',$projectRoot,'-OutputDir',(Join-Path $temp 'out'),'-RunId','C11-OK','-Version','not-version') $false 'P01_BUILD_INVALID_VERSION'
  $count++
  $exe=Join-Path $root 'NOX.P01.Shell.exe'
  [IO.File]::WriteAllBytes($exe,[byte[]](1,2,3,4,5,6,7))
  $record=[ordered]@{path='NOX.P01.Shell.exe';bytes=(Get-Item -LiteralPath $exe).Length;sha256=(Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()}
  $m=[ordered]@{schema='NOX_P01_PAYLOAD_SHA256_V1';entrypoint='NOX.P01.Shell.exe';runId='E01-C11-CI';version='0.1.0';files=@($record)}
  $manifest=Join-Path $root 'payload.sha256.json'
  ManifestToDisk $m $manifest
  ScriptCase $verifier @('-Root',$root,'-Manifest',$manifest) $true ''
  $count++
  $m.runId='P01-UNSET'
  ManifestToDisk $m $manifest
  ScriptCase $verifier @('-Root',$root,'-Manifest',$manifest) $false 'invalid run ID'
  $count++
  $m.runId='E01-C11-CI'
  $m.version='abc'
  ManifestToDisk $m $manifest
  ScriptCase $verifier @('-Root',$root,'-Manifest',$manifest) $false 'invalid version'
  $count++
  $m.version='0.1.0'
  $m.files[0].path='Uninstall.exe'
  ManifestToDisk $m $manifest
  ScriptCase $verifier @('-Root',$root,'-Manifest',$manifest) $false 'installer metadata'
  $count++
  $m.files[0].path='NOX.P01.Shell.exe'
  ManifestToDisk $m $manifest
  $elsewhere=Join-Path $root 'not-the-manifest.json'
  ManifestToDisk $m $elsewhere
  ScriptCase $verifier @('-Root',$root,'-Manifest',$elsewhere) $false 'noncanonical manifest'
  $count++
  Remove-Item -LiteralPath $elsewhere -Force
  $output = & powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $prereq
  Must ($LASTEXITCODE -eq 0) 'prerequisite failed'
  $info=($output -join [Environment]::NewLine) | ConvertFrom-Json
  Must ($info.downloadsPerformed -eq 0) 'download side effect'
  foreach ($item in @($info.requirements)) {
    if ($item.available -eq $true) {
      Must (Test-Path -LiteralPath ([string]$item.executable) -PathType Leaf) 'available without real EXE'
      $stat=Get-Item -LiteralPath $item.executable -Force
      Must (($stat.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) 'reparse prerequisite'
    }
  }
  $count++
  Must (Test-Path -LiteralPath $exe -PathType Leaf) 'verification deleted payload'
  $count++
  Write-Host "P01_C11_NATIVE_GUARDS_PASS=$count"
} finally {
  $check=[IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\')+'\'
  if ([IO.Path]::GetFullPath($temp).StartsWith($check,[StringComparison]::OrdinalIgnoreCase)) {
    Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
  }
}
