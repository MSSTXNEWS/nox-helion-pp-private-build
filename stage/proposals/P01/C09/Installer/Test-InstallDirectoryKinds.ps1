# Native source-only preflight fixture: no installer, application, or build invoked.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'WINDOWS_REQUIRED' }
$savedLocal = $env:LOCALAPPDATA
$fixture = Join-Path ([IO.Path]::GetTempPath()) ('P01-kind-test-' + [guid]::NewGuid().ToString('N'))
$script = Join-Path $PSScriptRoot 'Preflight-InstallPath.ps1'
try {
  foreach ($kind in @('root', 'stage', 'previous', 'rollback', 'programs', 'local', 'fresh', 'owned')) {
    $caseRoot = Join-Path $fixture $kind
    New-Item -ItemType Directory -Path $caseRoot -Force | Out-Null
    $env:LOCALAPPDATA = Join-Path $caseRoot 'Local'
    $programs = Join-Path $env:LOCALAPPDATA 'Programs'
    $root = Join-Path $programs 'NOX HELION'
    $obstruction = $null
    if ($kind -eq 'local') { $obstruction = $env:LOCALAPPDATA }
    else {
      New-Item -ItemType Directory -Path $env:LOCALAPPDATA -Force | Out-Null
      if ($kind -eq 'programs') { $obstruction = $programs }
      else {
        New-Item -ItemType Directory -Path $programs -Force | Out-Null
        if ($kind -eq 'root') { $obstruction = $root }
        elseif ($kind -ne 'fresh') {
          New-Item -ItemType Directory -Path $root -Force | Out-Null
          [IO.File]::WriteAllText((Join-Path $root 'nox-p01-owned.txt'), 'NOXHELION.P01 V16')
          switch ($kind) {
            'stage' { $obstruction = "$root.__p01_stage" }
            'previous' { $obstruction = "$root.__p01_previous" }
            'rollback' { $obstruction = "$root.__p01_rollback_saved" }
          }
        }
      }
    }
    if ($obstruction) {
      [IO.File]::WriteAllText($obstruction, 'unrelated existing file must survive preflight')
      $before = (Get-FileHash -LiteralPath $obstruction -Algorithm SHA256).Hash
      $caught = $null
      try { & $script -InstallRoot $root -PathOnly | Out-Null } catch { $caught = $_.Exception.Message }
      if (-not $caught -or -not $caught.StartsWith('P01_INSTALL_NOT_DIRECTORY:')) {
        throw "EXPECTED_DIRECTORY_REFUSAL:$kind got=$caught"
      }
      if ((Get-FileHash -LiteralPath $obstruction -Algorithm SHA256).Hash -cne $before) {
        throw "FILE_CHANGED_ON_PREFLIGHT_REFUSAL:$kind"
      }
    } else {
      $result = & $script -InstallRoot $root -PathOnly
      if ($result -ne 'P01_PATH_PREFLIGHT_PASS') { throw "VALID_DIRECTORY_CASE_REJECTED:$kind" }
    }
    Write-Output "P01_DIRECTORY_KIND_CASE_PASS:$kind"
  }
} finally {
  $env:LOCALAPPDATA = $savedLocal
  if (Test-Path -LiteralPath $fixture) { Remove-Item -LiteralPath $fixture -Recurse -Force }
}
