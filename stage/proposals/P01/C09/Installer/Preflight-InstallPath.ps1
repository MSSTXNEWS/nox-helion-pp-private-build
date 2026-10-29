[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$InstallRoot,
  [switch]$PathOnly
)
$ErrorActionPreference = 'Stop'
$expected = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs\NOX HELION'))
$root = [IO.Path]::GetFullPath($InstallRoot)
if ($root -ine $expected) { throw 'P01_INSTALL_ROOT_INVALID' }
foreach ($path in @($root, "$root.__p01_stage", "$root.__p01_previous", "$root.__p01_rollback_saved")) {
  if (Test-Path -LiteralPath $path) {
    $item = Get-Item -LiteralPath $path -Force
    if (-not $item.PSIsContainer) { throw "P01_INSTALL_NOT_DIRECTORY:$path" }
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "P01_INSTALL_REPARSE_POINT:$path" }
  }
}
# Never stage through a junction in the user-controlled install path or its parents.
$localRoot = [IO.Path]::GetFullPath($env:LOCALAPPDATA).TrimEnd('\')
foreach ($target in @($root, "$root.__p01_stage", "$root.__p01_previous", "$root.__p01_rollback_saved")) {
  $cursor = [IO.Path]::GetFullPath($target).TrimEnd('\')
  while ($cursor -and ($cursor -ieq $localRoot -or $cursor.StartsWith($localRoot+'\', [StringComparison]::OrdinalIgnoreCase))) {
    if (Test-Path -LiteralPath $cursor) {
      $node = Get-Item -LiteralPath $cursor -Force
      if (-not $node.PSIsContainer) { throw "P01_INSTALL_NOT_DIRECTORY:$cursor" }
      if (($node.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "P01_INSTALL_REPARSE_ANCESTOR:$cursor" }
    }
    if ($cursor -ieq $localRoot) { break }
    $cursor = [IO.Path]::GetDirectoryName($cursor)
  }
}
# Verify the existing installer-owned marker before allowing an update; a filename alone is not proof.
$marker = Join-Path $root 'nox-p01-owned.txt'
if (Test-Path -LiteralPath $root -PathType Container) {
  if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) { throw 'P01_INSTALL_EXISTING_UNOWNED' }
  $markerItem=Get-Item -LiteralPath $marker -Force -ErrorAction Stop
  if (($markerItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'P01_INSTALL_MARKER_REPARSE' }
  # Reject padded/trailing-data marker; ownership proof must match exact NSIS bytes.
  $want = [Text.Encoding]::ASCII.GetBytes('NOXHELION.P01 V16'+[char]13+[char]10)
  $actual = [IO.File]::ReadAllBytes($marker)
  if ($actual.Length -ne $want.Length -or
      [Convert]::ToBase64String($actual) -cne [Convert]::ToBase64String($want)) {
    throw 'P01_INSTALL_MARKER_INVALID'
  }
}
# Rollback needs identical path/ownership guards even when the runtime is unavailable.
if ($PathOnly) {
  'P01_PATH_PREFLIGHT_PASS'
  return
}
# Official Microsoft WebView2 runtime detection uses registry pv, not Edge browser presence.
$regPaths = @(
 'Registry::HKEY_CURRENT_USER\Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
 'Registry::HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
 'Registry::HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
)
$installed = $false
foreach ($p in $regPaths) {
  try {
    $v = (Get-ItemProperty -LiteralPath $p -ErrorAction Stop).pv
    # C11: WebView2 Runtime is present only with a parsable, nonzero version.
    if ($v) {
      try {
        $runtimeVersion=[version][string]$v
        if ($runtimeVersion.Major -gt 0) { $installed = $true; break }
      } catch { }
    }
  } catch { }
}
if (-not $installed) { throw 'P01_WEBVIEW2_RUNTIME_MISSING: Install official Microsoft Evergreen WebView2 Runtime first; no silent download.' }
'P01_PREFLIGHT_PASS'
