# E01 P01 C09 · Real Windows PowerShell 5.1 disposable component acceptance.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$SourceRoot)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if ($env:OS -ne 'Windows_NT' -or $env:CI -ne 'true' -or -not [Environment]::Is64BitOperatingSystem) { throw 'P01_C09_DISPOSABLE_WINDOWS_CI_ONLY' }
$source=[IO.Path]::GetFullPath($SourceRoot)
$uninstaller=Join-Path $source 'Installer\Remove-InstalledPayload.ps1'
$prereq=Join-Path $source 'Installer\Get-P01Prerequisites.ps1'
if (-not (Test-Path -LiteralPath $uninstaller -PathType Leaf)) { throw 'P01_C09_SOURCE_MISSING' }
$prefix=Join-Path $env:RUNNER_TEMP ('NOX_P01_C09_TEST_'+([guid]::NewGuid().ToString('N')))
$originalLocal=$env:LOCALAPPDATA
New-Item -ItemType Directory -Path $prefix | Out-Null
$passed=0
function Hash([string]$Path) { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Assert([bool]$Condition,[string]$Message) { if(-not $Condition){throw "P01_C09_TEST_FAILURE:$Message"} }
function New-Fixture([string]$Label) {
  $local=Join-Path $prefix $Label
  New-Item -ItemType Directory -Path $local | Out-Null
  $env:LOCALAPPDATA=$local
  $root=Join-Path $local 'Programs\NOX HELION'
  New-Item -ItemType Directory -Path (Join-Path $root 'data') -Force | Out-Null
  [IO.File]::WriteAllText((Join-Path $root 'nox-p01-owned.txt'),"NOXHELION.P01 V16`r`n")
  [IO.File]::WriteAllText((Join-Path $root 'data\a.txt'),'genuine-a')
  [IO.File]::WriteAllText((Join-Path $root 'data\z.txt'),'genuine-z')
  [IO.File]::WriteAllText((Join-Path $root 'user-created.txt'),'keep!')
  $records=@(Get-ChildItem -LiteralPath (Join-Path $root 'data') -File | ForEach-Object {
    [ordered]@{path='data/'+$_.Name;bytes=$_.Length;sha256=(Hash $_.FullName)}
  })
  # Synthetic text payload, never executable or launched: exercise required entrypoint identity.
  $entrypoint=Join-Path $root 'NOX.P01.Shell.exe'
  [IO.File]::WriteAllText($entrypoint,'C09 disposable non-PE entrypoint fixture')
  $records+=@([ordered]@{path='NOX.P01.Shell.exe';bytes=(Get-Item -LiteralPath $entrypoint).Length;sha256=(Hash $entrypoint)})
  $m=[ordered]@{schema='NOX_P01_PAYLOAD_SHA256_V1';entrypoint='NOX.P01.Shell.exe';runId='E01-C09-FIXTURE';version='0.1.0';files=$records}
  [IO.File]::WriteAllText((Join-Path $root 'payload.sha256.json'),($m | ConvertTo-Json -Depth 5))
  return [pscustomobject]@{Local=$local;Root=$root;Manifest=$m}
}
function Invoke-Uninstaller([pscustomobject]$Fixture,[bool]$ShouldPass,[string]$Case) {
  $env:LOCALAPPDATA=$Fixture.Local
  # Expected child stderr must not become a terminating parent error under pwsh 7.
  $formerPreference=$ErrorActionPreference
  $ErrorActionPreference='Continue'
  try {
    $output=& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $uninstaller -InstallRoot $Fixture.Root 2>&1
    $code=$LASTEXITCODE
  } finally { $ErrorActionPreference=$formerPreference }
  if($ShouldPass){Assert ($code -eq 0) "$Case expected success, got $code ($output)"}
  else {Assert ($code -ne 0) "$Case expected failure, got success"}
}
try {
  $t=New-Fixture 'tampered'
  [IO.File]::WriteAllText((Join-Path $t.Root 'data\z.txt'),'changed-late')
  Invoke-Uninstaller $t $false 'tampered-late'
  Assert (Test-Path -LiteralPath (Join-Path $t.Root 'data\a.txt')) 'tampered-early-file-deleted'
  Assert (Test-Path -LiteralPath (Join-Path $t.Root 'data\z.txt')) 'tampered-late-file-deleted'
  $passed++

  $t=New-Fixture 'missing'
  Remove-Item -LiteralPath (Join-Path $t.Root 'data\z.txt') -Force
  Invoke-Uninstaller $t $false 'missing-late'
  Assert (Test-Path -LiteralPath (Join-Path $t.Root 'data\a.txt')) 'missing-early-file-deleted'
  $passed++

  $t=New-Fixture 'duplicate'
  $t.Manifest.files=@($t.Manifest.files)+@($t.Manifest.files[0])
  [IO.File]::WriteAllText((Join-Path $t.Root 'payload.sha256.json'),($t.Manifest|ConvertTo-Json -Depth 6))
  Invoke-Uninstaller $t $false 'duplicate'
  Assert (Test-Path -LiteralPath (Join-Path $t.Root 'data\a.txt')) 'duplicate-early-file-deleted'
  $passed++

  $t=New-Fixture 'escape'
  $t.Manifest.files[1].path='../z.txt'
  [IO.File]::WriteAllText((Join-Path $t.Root 'payload.sha256.json'),($t.Manifest|ConvertTo-Json -Depth 6))
  Invoke-Uninstaller $t $false 'escape'
  Assert (Test-Path -LiteralPath (Join-Path $t.Root 'data\a.txt')) 'escape-early-file-deleted'
  $passed++

  $t=New-Fixture 'reserved'
  $t.Manifest.files[1].path='data/CON.txt'
  [IO.File]::WriteAllText((Join-Path $t.Root 'payload.sha256.json'),($t.Manifest|ConvertTo-Json -Depth 6))
  Invoke-Uninstaller $t $false 'reserved'
  Assert (Test-Path -LiteralPath (Join-Path $t.Root 'data\a.txt')) 'reserved-early-file-deleted'
  $passed++

  $t=New-Fixture 'bad-marker'
  [IO.File]::WriteAllText((Join-Path $t.Root 'nox-p01-owned.txt'),'not-owned')
  Invoke-Uninstaller $t $false 'owner-marker'
  Assert (Test-Path -LiteralPath (Join-Path $t.Root 'data\a.txt')) 'bad-marker-early-file-deleted'
  $passed++

  $t=New-Fixture 'bad-length'
  $t.Manifest.files[1].bytes=-1
  [IO.File]::WriteAllText((Join-Path $t.Root 'payload.sha256.json'),($t.Manifest|ConvertTo-Json -Depth 6))
  Invoke-Uninstaller $t $false 'bad-length'
  Assert (Test-Path -LiteralPath (Join-Path $t.Root 'data\a.txt')) 'bad-length-early-file-deleted'
  $passed++

  $t=New-Fixture 'bad-digest'
  $t.Manifest.files[1].sha256='z'*64
  [IO.File]::WriteAllText((Join-Path $t.Root 'payload.sha256.json'),($t.Manifest|ConvertTo-Json -Depth 6))
  Invoke-Uninstaller $t $false 'bad-digest'
  Assert (Test-Path -LiteralPath (Join-Path $t.Root 'data\a.txt')) 'bad-digest-early-file-deleted'
  $passed++

  $t=New-Fixture 'clean'
  Invoke-Uninstaller $t $true 'clean'
  Assert (-not (Test-Path -LiteralPath (Join-Path $t.Root 'data\a.txt'))) 'clean-payload-remained'
  Assert (-not (Test-Path -LiteralPath (Join-Path $t.Root 'data\z.txt'))) 'clean-payload-remained'
  Assert (-not (Test-Path -LiteralPath (Join-Path $t.Root 'NOX.P01.Shell.exe'))) 'clean-entrypoint-remained'
  Assert (Test-Path -LiteralPath (Join-Path $t.Root 'user-created.txt')) 'unknown-user-data-deleted'
  Assert (Test-Path -LiteralPath (Join-Path $t.Root 'nox-p01-owned.txt')) 'marker-removed-before-NSIS'
  Assert (Test-Path -LiteralPath (Join-Path $t.Root 'payload.sha256.json')) 'manifest-removed-before-NSIS'
  $passed++

  $t=New-Fixture 'prereq'
  $env:LOCALAPPDATA=$t.Local
  $prereqOutput=& powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $prereq
  Assert ($LASTEXITCODE -eq 0) 'prerequisite-probe-failed'
  $probe=($prereqOutput -join "`n") | ConvertFrom-Json
  Assert ($probe.schema -eq 'NOX_P01_PREREQUISITES_V1') 'prereq-schema'
  Assert (@($probe.requirements).Count -eq 4) 'prereq-not-four-tools'
  Assert ($probe.downloadsPerformed -eq 0) 'unapproved-downloads'
  $passed++
  Write-Host "P01_C09_NATIVE_POWERSHELL_PASS $passed/10 on $env:OS" -ForegroundColor Green
} finally {
  $env:LOCALAPPDATA=$originalLocal
  # Only private CI scratch created by this exact invocation is removed.
  if ($prefix.StartsWith([IO.Path]::GetFullPath($env:RUNNER_TEMP).TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)) {
    Remove-Item -LiteralPath $prefix -Recurse -Force -ErrorAction SilentlyContinue
  }
}
