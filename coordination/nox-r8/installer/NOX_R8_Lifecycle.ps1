# NOX HELION R8 B03: per-user NO-LOSS install/rollback, same WPF EXE only.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidateSet('Install','Rollback','Uninstall')][string]$Mode,
    [string]$Payload = '',
    [string]$ExpectedSha256 = '',
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'Programs\NOX_HELION')
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
function GuardPath([string]$p) {
    $q = [IO.Path]::GetFullPath($p)
    while ($q) {
        if ([IO.File]::Exists($q) -or [IO.Directory]::Exists($q)) {
            if (([IO.File]::GetAttributes($q) -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                throw 'NOX_INSTALL_REPARSE_HOLD'
            }
        }
        $parent = [IO.Directory]::GetParent($q)
        if ($null -eq $parent) { break }
        $q = $parent.FullName
    }
}
function HashFile([string]$p) {
    GuardPath $p
    if (-not [IO.File]::Exists($p)) { throw 'NOX_INSTALL_FILE_MISSING_HOLD' }
    # Windows PowerShell launched from NSIS can lack Get-FileHash autoload.
    # Use in-box .NET SHA256; dispose both file handle and hasher on all paths.
    $stream = [IO.File]::Open($p,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
    try {
        $hasher = [Security.Cryptography.SHA256]::Create()
        try { return [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-','') }
        finally { $hasher.Dispose() }
    } finally { $stream.Dispose() }
}
function ReadReceipt {
    $p = Join-Path $root 'NOX_INSTALL_RECEIPT.json'
    if (-not [IO.File]::Exists($p)) { return $null }
    GuardPath $p
    $r = Get-Content -LiteralPath $p -Raw | ConvertFrom-Json
    if ($r.schema -ne 'NOX_R8_INSTALL_NOLOSS_V1' -or $r.install_root -ne $root) {
        throw 'NOX_INSTALL_FOREIGN_RECEIPT_HOLD'
    }
    return $r
}
function SaveReceipt([string]$state,[string]$sha,[string]$previous,[string]$previousSha) {
    $p = Join-Path $root 'NOX_INSTALL_RECEIPT.json'
    $temp = Join-Path $root ('NOX_INSTALL_RECEIPT.'+[guid]::NewGuid().ToString('N')+'.partial')
    $record = @{
        schema='NOX_R8_INSTALL_NOLOSS_V1'; state=$state; install_root=$root
        current_sha256=$sha; previous_file=$previous; previous_sha256=$previousSha
        checked_utc=[DateTimeOffset]::UtcNow.ToString('O')
        owner_data_preserved=$true; real_qwen_e2e='NOT_TESTED_BY_INSTALLER'
    }
    [IO.File]::WriteAllText($temp,($record|ConvertTo-Json),[Text.UTF8Encoding]::new($false))
    GuardPath $root
    if ([IO.File]::Exists($p)) {
        GuardPath $p
        $old = Join-Path $root ('NOX_INSTALL_RECEIPT.previous.'+[guid]::NewGuid().ToString('N')+'.json')
        [IO.File]::Replace($temp,$p,$old,$true)
    } else { [IO.File]::Move($temp,$p) }
    $check = ReadReceipt
    if ($check.current_sha256 -ne $sha -or $check.state -ne $state) {
        throw 'NOX_INSTALL_RECEIPT_READBACK_HOLD'
    }
}
function GuardManaged($receipt) {
    if ([IO.File]::Exists($target)) {
        if ($null -eq $receipt -or
            $receipt.current_sha256 -notmatch '^[a-fA-F0-9]{64}$' -or
            (HashFile $target) -ne $receipt.current_sha256) {
            throw 'NOX_INSTALL_UNMANAGED_OWNER_BINARY_HOLD'
        }
    } elseif ($null -ne $receipt -and $receipt.state -ne 'uninstalled') {
        throw 'NOX_INSTALL_MISSING_MANAGED_BINARY_HOLD'
    }
}
if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) { throw 'NOX_INSTALL_NO_LOCALAPPDATA_HOLD' }
$private = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs')).TrimEnd('\')
$root = [IO.Path]::GetFullPath($InstallRoot).TrimEnd('\')
if (-not $root.StartsWith($private+'\', [StringComparison]::OrdinalIgnoreCase)) {
    throw 'NOX_INSTALL_OUTSIDE_PRIVATE_PROGRAMS_HOLD'
}
GuardPath $root
$target = Join-Path $root 'NOX.HELION.exe'
$shaObj = [Security.Cryptography.SHA256]::Create()
try { $id = [BitConverter]::ToString($shaObj.ComputeHash([Text.Encoding]::UTF8.GetBytes($root.ToUpperInvariant()))).Replace('-','').Substring(0,24) }
finally { $shaObj.Dispose() }
$mutex = [Threading.Mutex]::new($false,('Local\NOX_R8_INSTALL_'+$id))
$held = $false
try {
    try { $held = $mutex.WaitOne([TimeSpan]::FromSeconds(20)) }
    catch [Threading.AbandonedMutexException] { $held = $true }
    if (-not $held) { throw 'NOX_INSTALL_CONCURRENT_HOLD' }
    GuardPath $root
    if ($Mode -eq 'Install') {
        if ($ExpectedSha256 -notmatch '^[a-fA-F0-9]{64}$' -or
            [string]::IsNullOrWhiteSpace($Payload)) { throw 'NOX_INSTALL_UNPINNED_HOLD' }
        $sha = $ExpectedSha256.ToUpperInvariant()
        if ((HashFile $Payload) -ne $sha) { throw 'NOX_INSTALL_PAYLOAD_HASH_HOLD' }
        [IO.Directory]::CreateDirectory($root) | Out-Null
        GuardPath $root
        $receipt = ReadReceipt
        GuardManaged $receipt
        if (@(Get-Process -Name 'NOX.HELION' -ErrorAction SilentlyContinue).Count -gt 0) {
            throw 'NOX_INSTALL_RUNNING_PROCESS_HOLD'
        }
        $tag = [guid]::NewGuid().ToString('N')
        $incoming = Join-Path $root ('NOX.HELION.incoming.'+$tag+'.exe')
        [IO.File]::Copy($Payload,$incoming,$false)
        $oldPath = ''; $oldHash = ''
        try {
            if ((HashFile $incoming) -ne $sha) { throw 'NOX_INSTALL_STAGED_HASH_HOLD' }
            if ([IO.File]::Exists($target)) {
                $oldHash = HashFile $target
                $oldPath = Join-Path $root ('NOX.HELION.previous.'+$oldHash+'.'+$tag+'.exe')
                [IO.File]::Move($target,$oldPath)
            }
            [IO.File]::Move($incoming,$target)
            if ((HashFile $target) -ne $sha) { throw 'NOX_INSTALL_ACTIVATED_HASH_HOLD' }
            SaveReceipt 'installed' $sha ([IO.Path]::GetFileName($oldPath)) $oldHash
        } catch {
            if ([IO.File]::Exists($target) -and (HashFile $target) -eq $sha) {
                [IO.File]::Move($target,(Join-Path $root ('NOX.HELION.displaced.'+$tag+'.exe')))
            }
            if ($oldPath -and [IO.File]::Exists($oldPath) -and -not [IO.File]::Exists($target)) {
                [IO.File]::Move($oldPath,$target)
            }
            throw
        }
        Write-Output ('NOX_INSTALL_MANAGED_SHA256='+$sha)
    } else {
        if (-not [IO.Directory]::Exists($root)) { throw 'NOX_INSTALL_NOT_FOUND_HOLD' }
        $receipt = ReadReceipt
        if ($null -eq $receipt) { throw 'NOX_INSTALL_NO_RECEIPT_HOLD' }
        GuardManaged $receipt
        if (@(Get-Process -Name 'NOX.HELION' -ErrorAction SilentlyContinue).Count -gt 0) {
            throw 'NOX_INSTALL_RUNNING_PROCESS_HOLD'
        }
        if ($Mode -eq 'Rollback') {
            if ($receipt.previous_file -notmatch '^NOX[.]HELION[.]previous[.][A-F0-9]{64}[.][a-f0-9]{32}[.]exe$' -or
                $receipt.previous_sha256 -notmatch '^[A-F0-9]{64}$') {
                throw 'NOX_INSTALL_NO_VERIFIED_ROLLBACK_HOLD'
            }
            $old = Join-Path $root $receipt.previous_file
            if ((HashFile $old) -ne $receipt.previous_sha256) {
                throw 'NOX_INSTALL_ROLLBACK_HASH_HOLD'
            }
            $displaced = Join-Path $root ('NOX.HELION.displaced.'+[guid]::NewGuid().ToString('N')+'.exe')
            [IO.File]::Move($target,$displaced)
            try {
                [IO.File]::Move($old,$target)
                if ((HashFile $target) -ne $receipt.previous_sha256) {
                    throw 'NOX_INSTALL_ROLLBACK_READBACK_HOLD'
                }
                SaveReceipt 'installed' $receipt.previous_sha256 '' ''
            } catch {
                if (-not [IO.File]::Exists($target)) { [IO.File]::Move($displaced,$target) }
                throw
            }
            Write-Output ('NOX_INSTALL_ROLLBACK_SHA256='+$receipt.previous_sha256)
        } else {
            # Explicit NSIS uninstall: ONLY verified managed EXE; retain memory,
            # user %LOCALAPPDATA%\NOX_HELION, rollback files and audit receipts.
            if ([IO.File]::Exists($target)) { [IO.File]::Delete($target) }
            SaveReceipt 'uninstalled' '' $receipt.previous_file $receipt.previous_sha256
            Write-Output 'NOX_INSTALL_OWNER_DATA_PRESERVED'
        }
    }
} finally {
    if ($held) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
