# D06: real Windows runner NTFS SID/DACL test on the two-process isolated SQLite.
# No owner chat.sqlite3 is opened, modified, backed up, or deleted.
param(
  [Parameter(Mandatory=$true)][ValidatePattern('^NOX-R8-[0-9]+$')][string]$RunId,
  [Parameter(Mandatory=$true)][string]$ExePath
)
$ErrorActionPreference='Stop'
if (-not $IsWindows) { throw 'NOX_D06_SID_ACL_WINDOWS_ONLY_HOLD' }
$exe=(Resolve-Path -LiteralPath $ExePath -ErrorAction Stop).Path
$exeSha=(Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
$identity=[System.Security.Principal.WindowsIdentity]::GetCurrent()
if ($null -eq $identity.User) { throw 'NOX_D06_OWNER_SID_UNAVAILABLE_HOLD' }
$ownerSid=$identity.User.Value
$home=Join-Path $env:LOCALAPPDATA 'NOX_HELION'
$hex=[Convert]::ToHexString([System.Security.Cryptography.SHA256]::HashData(
  [System.Text.Encoding]::UTF8.GetBytes($RunId)))
$db=Join-Path $home ('selftest_r8_'+$hex.Substring(0,32)+'.sqlite3')
$root=[IO.Path]::GetFullPath($home)
$dbFull=[IO.Path]::GetFullPath($db)
$ownerDb=[IO.Path]::GetFullPath((Join-Path $home 'chat.sqlite3'))
if (-not $dbFull.StartsWith($root+[IO.Path]::DirectorySeparatorChar,
    [StringComparison]::OrdinalIgnoreCase) -or
    [string]::Equals($dbFull,$ownerDb,[StringComparison]::OrdinalIgnoreCase)) {
  throw 'NOX_D06_ISOLATED_SQLITE_PATH_HOLD'
}
if (-not (Test-Path -LiteralPath $db -PathType Leaf) -or
    (Get-Item -LiteralPath $db).Length -le 0) {
  throw 'NOX_D06_ISOLATED_SQLITE_MISSING_HOLD'
}
# Only broad mutating ALLOW ACEs fail the gate; read-only inherited grants are fine.
# No cross-user access-token impersonation is claimed by this isolated CI check.
$broad=@('S-1-1-0','S-1-5-11','S-1-5-32-545','S-1-5-32-546','S-1-15-2-1')
$writeBits=([int][System.Security.AccessControl.FileSystemRights]::WriteData) -bor
  ([int][System.Security.AccessControl.FileSystemRights]::AppendData) -bor
  ([int][System.Security.AccessControl.FileSystemRights]::WriteExtendedAttributes) -bor
  ([int][System.Security.AccessControl.FileSystemRights]::WriteAttributes) -bor
  ([int][System.Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles) -bor
  ([int][System.Security.AccessControl.FileSystemRights]::Delete) -bor
  ([int][System.Security.AccessControl.FileSystemRights]::ChangePermissions) -bor
  ([int][System.Security.AccessControl.FileSystemRights]::TakeOwnership)
foreach ($path in @($home,$db)) {
  $acl=Get-Acl -LiteralPath $path -ErrorAction Stop
  if ($acl.GetOwner([System.Security.Principal.SecurityIdentifier]).Value -cne $ownerSid) {
    throw 'NOX_D06_NTFS_OWNER_SID_MISMATCH_HOLD'
  }
  if (@($acl.Access).Count -eq 0) { throw 'NOX_D06_NTFS_DACL_EMPTY_HOLD' }
  foreach ($ace in @($acl.Access)) {
    if ($ace.AccessControlType -ne [System.Security.AccessControl.AccessControlType]::Allow) {
      continue
    }
    try {
      $sid=$ace.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value
    } catch { throw 'NOX_D06_NTFS_ACE_PRINCIPAL_UNRESOLVED_HOLD' }
    if (($broad -contains $sid) -and (([int]$ace.FileSystemRights -band $writeBits) -ne 0)) {
      throw 'NOX_D06_NTFS_BROAD_WRITE_ALLOW_HOLD'
    }
  }
}
$receipt=[ordered]@{
  schema='NOX_R8_SETTINGS_ISOLATED_SID_ACL_CI_V1'
  source_sha=$env:GITHUB_SHA
  run_id=$RunId
  exe_sha256=$exeSha
  checked_at=[DateTimeOffset]::UtcNow.ToString('O')
  sqlite_owner_sid='PASS'
  sqlite_parent_owner_sid='PASS'
  no_broad_mutating_ace='PASS'
  owner_pc_acl='NOT_TESTED'
  cross_user_access_denial='NOT_TESTED'
}
New-Item -ItemType Directory -Path './out' -Force | Out-Null
$receipt | ConvertTo-Json -Depth 4 |
  Set-Content -LiteralPath './out/SETTINGS_ISOLATED_SID_ACL_RECEIPT.json' -Encoding utf8
Write-Host "NOX_R8_SETTINGS_ISOLATED_SID_ACL_CI_PASS SHA256=$exeSha (owner PC and cross-user denial not tested)"
