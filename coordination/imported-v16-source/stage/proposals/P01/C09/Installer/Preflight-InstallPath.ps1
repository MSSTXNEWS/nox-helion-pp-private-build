[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$InstallRoot)
$ErrorActionPreference = 'Stop'
$expected = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs\NOX HELION'))
$root = [IO.Path]::GetFullPath($InstallRoot)
if ($root -ine $expected) { throw 'P01_INSTALL_ROOT_INVALID' }
foreach ($path in @($root, "$root.__p01_stage", "$root.__p01_previous", "$root.__p01_rollback_saved")) {
  if (Test-Path -LiteralPath $path) {
    $item = Get-Item -LiteralPath $path -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "P01_INSTALL_REPARSE_POINT:$path" }
  }
}
# Never stage through a junction in the install path OR an upstream
# ancestor, including parents above LOCALAPPDATA (same policy as P01
# Verify-Payload and Remove-InstalledPayload). No new installation rights.
foreach ($target in @($root, "$root.__p01_stage", "$root.__p01_previous", "$root.__p01_rollback_saved")) {
  $cursor = [IO.Path]::GetFullPath($target).TrimEnd('\')
  while ($cursor) {
    if (Test-Path -LiteralPath $cursor) {
      $node = Get-Item -LiteralPath $cursor -Force -ErrorAction Stop
      if (-not $node.PSIsContainer -or
          (($node.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0)) {
        throw "P01_INSTALL_REPARSE_ANCESTOR:$cursor"
      }
    }
    $next = [IO.Path]::GetDirectoryName($cursor)
    if ([string]::IsNullOrEmpty($next) -or $next -ceq $cursor) { break }
    $cursor = $next
  }
}
# Verify the existing installer-owned marker before allowing an update; a filename alone is not proof.
$marker = Join-Path $root 'nox-p01-owned.txt'
if (Test-Path -LiteralPath $root -PathType Container) {
  if (-not (Test-Path -LiteralPath $marker -PathType Leaf)) { throw 'P01_INSTALL_EXISTING_UNOWNED' }
  $markerItem=Get-Item -LiteralPath $marker -Force -ErrorAction Stop
  if (($markerItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'P01_INSTALL_MARKER_REPARSE' }
  if ((Get-Content -LiteralPath $marker -Raw -Encoding UTF8).Trim() -cne 'NOXHELION.P01 V16') { throw 'P01_INSTALL_MARKER_INVALID' }
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
# E06: real Windows native winreg found HKLM_32_VIEW pv=156.0.4314.58
# while provider-only PowerShell preflight reported MISSING. Resolve the same
# official runtime key through an explicit .NET 32-bit view, independent of
# current PowerShell process bitness. Keep original probes and fail-closed gate.
# This is registry presence only: native WPF WebView2 initialization is still
# mandatory at installed smoke/E07; never accept an Edge browser as runtime.
if (-not $installed) {
  $hklm32=$null
  $client32=$null
  try {
    $hklm32=[Microsoft.Win32.RegistryKey]::OpenBaseKey(
      [Microsoft.Win32.RegistryHive]::LocalMachine,
      [Microsoft.Win32.RegistryView]::Registry32)
    $client32=$hklm32.OpenSubKey(
      'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', $false)
    if ($null -ne $client32 -and
        $client32.GetValueKind('pv') -eq [Microsoft.Win32.RegistryValueKind]::String) {
      $pv32=$client32.GetValue('pv', $null,
        [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
      if ($pv32 -is [string]) {
        try {
          $runtimeVersion32=[version]$pv32
          if ($runtimeVersion32.Major -gt 0) { $installed=$true }
        } catch { }
      }
    }
  } catch { } finally {
    if ($null -ne $client32) { $client32.Dispose() }
    if ($null -ne $hklm32) { $hklm32.Dispose() }
  }
}
if (-not $installed) { throw 'P01_WEBVIEW2_RUNTIME_MISSING: Install official Microsoft Evergreen WebView2 Runtime first; no silent download.' }
'P01_PREFLIGHT_PASS'
