#requires -Version 5.1
<#
Copies a transaction-consistent NOX SQLite snapshot and stable model/checkpoint
files to this PC first, then Google Drive when available. A verified PC backup
survives Drive quota/authentication/transfer failure. Full SHA-256 readback of
both external copies still precedes any requested inactive GGUF removal.
Run from a normal Windows PowerShell window. Credentials stay on this PC and in
one mode-0600 rclone config on the owner's server; never paste them into chat.
Google Drive setup may require your own Desktop OAuth client ID (rclone's shared
client is being retired). The new remote uses drive.file, not whole-Drive scope.
A root_folder_id selects a folder; it is not a security boundary for OAuth.
#>
[CmdletBinding()]
param(
    [string]$DestinationRoot = 'C:\NOX_HELION',
    [string]$SshKeyPath = '',
    [string]$GoogleClientId = '',
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$')][string]$SessionId = '',
    [ValidateSet('PreferDrive','PcOnly')][string]$StoragePolicy = 'PreferDrive',
    [switch]$EvictInactiveModels
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$InstanceId = 60509551
$HostPin = 'SHA256:G4hmMllaT4uSfx+Gup9vjSySLXJT1cSc/9XePr7XmGc'
$DestinationRoot = [IO.Path]::GetFullPath($DestinationRoot)
$Access = Join-Path $DestinationRoot 'ACCESS'
$Config = Join-Path $Access 'nox-transfer.conf'
$KnownHosts = Join-Path $Access 'known_hosts'
$StateFile = Join-Path $DestinationRoot 'transfer-state.json'
$Helper = Join-Path $PSScriptRoot 'nox_pc_export.py'
$ColdHelper = Join-Path $PSScriptRoot 'nox_cold_drive.py'
$Utf8 = New-Object System.Text.UTF8Encoding -ArgumentList $false
$PlainApiKey = $null
$GoogleSecret = $null

function Write-PlainFile([string]$Path, [string]$Value) {
    [IO.File]::WriteAllText($Path, $Value, $Utf8)
}
function Protect-Folder([string]$Path) {
    $null = New-Item -ItemType Directory -Force -Path $Path
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    & icacls.exe $Path /inheritance:r /grant:r "*${sid}:(OI)(CI)F" '*S-1-5-18:(OI)(CI)F' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not restrict the local credential folder.' }
}
function Unwrap-Secure([Security.SecureString]$Value) {
    $p = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($p) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($p) }
}
function Quote-Native([string]$Value) {
    # Windows CommandLineToArgvW convention, including an empty -N argument.
    return '"' + ([regex]::Replace([regex]::Replace($Value, '(\\*)"', '$1$1\"'), '(\\+)$', '$1$1')) + '"'
}
function New-Native([string]$Program, [string[]]$Argv) {
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = $Program
    $info.Arguments = (($Argv | ForEach-Object { Quote-Native $_ }) -join ' ')
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $info
    $null = $process.Start()
    return $process
}
function Native-Capture([string]$Program, [string[]]$Argv) {
    $process = New-Native $Program $Argv
    try {
        $errTask = $process.StandardError.ReadToEndAsync()
        $output = $process.StandardOutput.ReadToEnd()
        $process.WaitForExit()
        $null = $errTask.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0) { throw "Native command failed: $([IO.Path]::GetFileName($Program)), exit $($process.ExitCode). Provider output was withheld to protect credentials." }
        return $output
    } finally { $process.Dispose() }
}
function Invoke-Rclone([string[]]$Argv) {
    & $script:Rclone @Argv --config $Config
    if ($LASTEXITCODE -ne 0) { throw "rclone failed with exit $LASTEXITCODE. No eviction has been authorized by this failed step." }
}
function Capture-Rclone([string[]]$Argv) {
    return Native-Capture $script:Rclone ($Argv + @('--config', $Config))
}
function Invoke-Ssh([string]$Command) {
    & ssh.exe @script:SshArguments $script:Target $Command
    if ($LASTEXITCODE -ne 0) { throw "NOX server command failed (exit $LASTEXITCODE)." }
}
function Copy-ToServer([string]$Local, [string]$Remote) {
    & scp.exe @script:ScpArguments $Local "${script:Target}:$Remote"
    if ($LASTEXITCODE -ne 0) { throw 'SCP upload failed.' }
}
function Copy-FromServer([string]$Remote, [string]$Local) {
    & scp.exe @script:ScpArguments "${script:Target}:$Remote" $Local
    if ($LASTEXITCODE -ne 0) { throw 'SCP download failed.' }
}
function Vast-Request([string]$Method, [string]$Path, $Payload = $null) {
    $request = @{ Method=$Method; Uri=('https://console.vast.ai/api/' + $Path);
               Headers=@{Authorization=('Bearer ' + $script:PlainApiKey); Accept='application/json'}; TimeoutSec=45 }
    if ($null -ne $Payload) { $request.Body = ($Payload | ConvertTo-Json -Compress); $request.ContentType='application/json' }
    try { return Invoke-RestMethod @request }
    catch { throw "Vast owner API request failed ($Method). Check your local API key and ownership of instance 60509551." }
}
function Get-Field($Object, [string]$Name, $Default = $null) {
    if ($null -eq $Object) { return $Default }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -eq $property) { return $Default }
    return $property.Value
}
function Relative-Local([string]$Rel, [string]$Root) {
    if ([string]::IsNullOrEmpty($Rel) -or $Rel -match '(^/|\\|:|[\x00-\x1f]|(^|/)\.\.(/|$))') { throw 'Unsafe backup manifest path.' }
    $result = [IO.Path]::GetFullPath((Join-Path $Root ($Rel.Replace('/', '\'))))
    if (-not $result.StartsWith($Root.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Manifest path escaped the backup root.' }
    return $result
}
function Readback-Sha([string]$Remote, [long]$ExpectedBytes) {
    # Read the binary BaseStream directly. PowerShell's text pipe corrupts weights.
    $process = New-Native $script:Rclone @('cat', $Remote, '--config', $Config, '--timeout', '2m', '--contimeout', '30s', '--retries', '2', '--low-level-retries', '2')
    $hash = [Security.Cryptography.SHA256]::Create()
    $buffer = New-Object byte[] (1024*1024)
    [long]$total = 0
    try {
        $errTask = $process.StandardError.ReadToEndAsync()
        while (($n = $process.StandardOutput.BaseStream.Read($buffer, 0, $buffer.Length)) -gt 0) {
            $total += $n
            if ($total -gt $ExpectedBytes) { throw 'Drive readback exceeds the expected size.' }
            $null = $hash.TransformBlock($buffer, 0, $n, $buffer, 0)
        }
        $null = $hash.TransformFinalBlock($buffer, 0, 0)
        $process.WaitForExit()
        $null = $errTask.GetAwaiter().GetResult()
        if ($process.ExitCode -ne 0 -or $total -ne $ExpectedBytes) { throw 'Drive readback did not complete.' }
        return ([BitConverter]::ToString($hash.Hash).Replace('-', '').ToLowerInvariant())
    } finally {
        if (-not $process.HasExited) { $process.Kill(); $process.WaitForExit() }
        $hash.Dispose(); $process.Dispose()
    }
}

function Initialize-Drive {
    $existingNames = @((Capture-Rclone @('listremotes')).Trim() -split '\r?\n')
    if ($existingNames -notcontains 'nox_drive:') {
        Write-Host 'A browser will request access to files created/opened by this rclone app. Use your own Google account.'
        if ([string]::IsNullOrWhiteSpace($GoogleClientId)) {
            $GoogleClientId = Read-Host 'Google Desktop OAuth client ID (Enter to try the retiring shared rclone client)'
        }
        $setup = @('config','create','nox_drive','drive','scope','drive.file','config_is_local','true')
        if (-not [string]::IsNullOrWhiteSpace($GoogleClientId)) {
            $secret = Read-Host 'Google Desktop OAuth client secret (local only)' -AsSecureString
            $GoogleSecret = Unwrap-Secure $secret
            $secret.Dispose()
            # Pass OAuth app secrets by environment, not command-line arguments.
            $env:RCLONE_CONFIG_NOX_DRIVE_CLIENT_ID = $GoogleClientId
            $env:RCLONE_CONFIG_NOX_DRIVE_CLIENT_SECRET = $GoogleSecret
        }
        try {
            Invoke-Rclone $setup | Out-Null
            if (-not [string]::IsNullOrWhiteSpace($GoogleClientId)) {
                if ($GoogleClientId -match '[\r\n]' -or $GoogleSecret -match '[\r\n]') { throw 'OAuth application values must be single-line.' }
                # Environment overrides are not guaranteed to be written by rclone.
                # Save them explicitly for refresh on both PC and server.
                # OAuth client_secret is a Sensitive string, not an IsPassword
                # field in rclone. Obscuring it would break OAuth token refresh.
                $configText = [IO.File]::ReadAllText($Config)
                $section = [regex]::Match($configText, '(?ms)^\[nox_drive\]\s*\r?\n(.*?)(?=^\[|\z)')
                if (-not $section.Success) { throw 'OAuth did not create the dedicated remote.' }
                $body = $section.Groups[1].Value -replace '(?m)^(client_id|client_secret)\s*=.*\r?\n?', ''
                $replacement = "[nox_drive]`nclient_id = $GoogleClientId`nclient_secret = $GoogleSecret`n" + $body
                $configText = $configText.Substring(0,$section.Index) + $replacement + $configText.Substring($section.Index+$section.Length)
                Write-PlainFile $Config $configText
            }
        }
        finally {
            Remove-Item Env:RCLONE_CONFIG_NOX_DRIVE_CLIENT_ID -ErrorAction SilentlyContinue
            Remove-Item Env:RCLONE_CONFIG_NOX_DRIVE_CLIENT_SECRET -ErrorAction SilentlyContinue
            $GoogleSecret = $null
        }
    }
    $privateConfig = [IO.File]::ReadAllText($Config)
    $driveSection = [regex]::Match($privateConfig, '(?ms)^\[nox_drive\]\s*\r?\n(.*?)(?=^\[|\z)')
    if (-not $driveSection.Success -or $driveSection.Groups[1].Value -notmatch '(?m)^scope\s*=\s*drive\.file\s*$') { throw 'nox_drive must use drive.file. Use a dedicated config with the required scope.' }
    if ($driveSection.Groups[1].Value -notmatch '(?m)^root_folder_id\s*=\s*\S+') {
        $folderName = 'NOX_SERVER_60509551_COLD'
        $null = Capture-Rclone @('mkdir',"nox_drive:$folderName")
        $folders = (Capture-Rclone @('lsjson','nox_drive:','--dirs-only','--max-depth','1')) | ConvertFrom-Json
        $selected = @($folders | Where-Object { $_.Name -ceq $folderName })
        if ($selected.Count -ne 1 -or [string]::IsNullOrWhiteSpace([string]$selected[0].ID)) { throw 'Dedicated Drive folder lookup is ambiguous.' }
        $null = Capture-Rclone @('config','update','nox_drive','root_folder_id',([string]$selected[0].ID))
    }
    $null = Capture-Rclone @('lsjson','nox_drive:','--max-depth','1')
}

try {
    if ($env:OS -ne 'Windows_NT') { throw 'Run this script on your Windows PC.' }
    foreach ($tool in @('ssh.exe','scp.exe','ssh-keygen.exe','ssh-keyscan.exe','icacls.exe')) {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "Install Windows OpenSSH Client first; missing $tool." }
    }
    if (-not (Test-Path -LiteralPath $Helper -PathType Leaf)) { throw 'Keep nox_pc_export.py beside this script.' }
    $null = New-Item -ItemType Directory -Force -Path $DestinationRoot
    Protect-Folder $Access
    if ([string]::IsNullOrEmpty($SshKeyPath)) { $SshKeyPath = Join-Path $Access 'NOX_VAST_SSH_ed25519' }
    $SshKeyPath = [IO.Path]::GetFullPath($SshKeyPath)
    if (-not (Test-Path -LiteralPath $SshKeyPath)) {
        $null = Native-Capture 'ssh-keygen.exe' @('-q','-t','ed25519','-N','','-C','NOX-owner-PC-60509551','-f',$SshKeyPath)
    }
    if (-not (Test-Path -LiteralPath ($SshKeyPath + '.pub'))) { throw 'An existing SSH key must have its .pub file.' }
    $PublicKey = [IO.File]::ReadAllText($SshKeyPath + '.pub').Trim()
    if ($PublicKey -notmatch '^ssh-ed25519 [A-Za-z0-9+/=]+(?: .*)?$') { throw 'Use an ed25519 owner SSH key.' }
    $PlainApiKey = [Environment]::GetEnvironmentVariable('VAST_API_KEY')
    if ([string]::IsNullOrWhiteSpace($PlainApiKey)) {
        Write-Host 'Enter your Vast owner API key locally. It will not be stored in the script or sent to chat.'
        $secret = Read-Host 'Vast API key' -AsSecureString
        $PlainApiKey = Unwrap-Secure $secret
        $secret.Dispose()
    }
    if ([string]::IsNullOrWhiteSpace($PlainApiKey)) { throw 'Vast owner authentication is required.' }
    $listing = Vast-Request 'GET' 'v1/instances/?owner=me'
    $instances = Get-Field $listing 'instances' $listing
    $ownedMatches = @($instances | Where-Object { [long](Get-Field $_ 'id' -1) -eq $InstanceId })
    if ($ownedMatches.Count -ne 1) { throw 'Exactly one owned instance 60509551 is required.' }
    $instance = $ownedMatches[0]
    if ((Get-Field $instance 'actual_status' '') -ne 'running') { throw 'Instance 60509551 is not running. This script does not rent or start another instance.' }
    $ServerHost = [string](Get-Field $instance 'public_ipaddr' '')
    $parsedIp = $null
    if (-not [Net.IPAddress]::TryParse($ServerHost, [ref]$parsedIp) -or $parsedIp.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork) { throw 'No verified public IPv4 route in the owner API.' }
    $ports = Get-Field $instance 'ports'
    if ($null -eq $ports) { throw 'Instance has no SSH port mapping.' }
    $sshPorts = @(Get-Field $ports '22/tcp' @())
    $portNumbers = @($sshPorts | ForEach-Object { [int](Get-Field $_ 'HostPort' 0) } | Where-Object { $_ -gt 0 -and $_ -le 65535 } | Select-Object -Unique)
    if ($portNumbers.Count -ne 1) { throw 'Exactly one SSH route is required.' }
    $ServerPort = $portNumbers[0]
    $keyResponse = Vast-Request 'GET' "v0/instances/$InstanceId/ssh/"
    $keys = Get-Field $keyResponse 'ssh_keys' (Get-Field $keyResponse 'keys' $keyResponse)
    if ($keys -is [string]) { $keys = $keys | ConvertFrom-Json }
    $publicIdentity = (($PublicKey -split '\s+')[0..1] -join ' ')
    $attached = @($keys | Where-Object {
        $k = [string](Get-Field $_ 'public_key' (Get-Field $_ 'ssh_key' (Get-Field $_ 'key' '')))
        $fields = $k -split '\s+'
        $fields.Count -ge 2 -and (($fields[0..1] -join ' ') -eq $publicIdentity)
    })
    if ($attached.Count -eq 0) { $null = Vast-Request 'POST' "v0/instances/$InstanceId/ssh/" @{ssh_key=$PublicKey} }
    $PlainApiKey = $null
    $candidate = Native-Capture 'ssh-keyscan.exe' @('-T','15','-p',"$ServerPort",'-t','ed25519',$ServerHost)
    $candidateFile = Join-Path $Access 'known_hosts.candidate'
    Write-PlainFile $candidateFile $candidate
    $fingerprint = Native-Capture 'ssh-keygen.exe' @('-l','-f',$candidateFile,'-E','sha256')
    $pins = @([regex]::Matches($fingerprint, 'SHA256:[A-Za-z0-9+/=]+') | ForEach-Object { $_.Value } | Select-Object -Unique)
    if ($pins.Count -ne 1 -or $pins[0] -cne $HostPin) { throw 'SSH host pin mismatch. No credential or data transfer was attempted.' }
    Write-PlainFile $KnownHosts $candidate
    $Target = "root@$ServerHost"
    # OpenSSH parses this option once more as a filename list. Preserve literal
    # quotes around a custom backup path containing spaces for that second parse.
    $PinnedKnownHostsOption = 'UserKnownHostsFile="' + $KnownHosts.Replace('\','/') + '"'
    $SshArguments = @('-i',$SshKeyPath,'-p',"$ServerPort",'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o',$PinnedKnownHostsOption,'-o','ConnectTimeout=30')
    $ScpArguments = @('-i',$SshKeyPath,'-P',"$ServerPort",'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o',$PinnedKnownHostsOption,'-o','ConnectTimeout=30')
    Invoke-Ssh 'test -d /root/nox && command -v python3 && command -v rclone'

    $rcloneCommand = Get-Command 'rclone.exe' -ErrorAction SilentlyContinue
    if ($rcloneCommand) { $Rclone = $rcloneCommand.Source }
    else {
        $toolsFolder = Join-Path $DestinationRoot 'TOOLS'
        $null = New-Item -ItemType Directory -Force -Path $toolsFolder
        $versionText = (Invoke-WebRequest -UseBasicParsing 'https://downloads.rclone.org/version.txt').Content.Trim()
        if ($versionText -notmatch '^rclone (v\d+\.\d+\.\d+)$') { throw 'Unexpected rclone version metadata.' }
        $version = $Matches[1]
        $zipName = "rclone-$version-windows-amd64.zip"
        $zip = Join-Path $toolsFolder $zipName
        $checksums = (Invoke-WebRequest -UseBasicParsing "https://downloads.rclone.org/$version/SHA256SUMS").Content
        $match = [regex]::Match($checksums, '(?m)^([0-9a-fA-F]{64})\s+\*?' + [regex]::Escape($zipName) + '\s*$')
        if (-not $match.Success) { throw 'The official rclone checksum list is missing the Windows archive.' }
        Invoke-WebRequest -UseBasicParsing "https://downloads.rclone.org/$version/$zipName" -OutFile $zip
        if ((Get-FileHash -Algorithm SHA256 -LiteralPath $zip).Hash -ine $match.Groups[1].Value) { throw 'rclone archive SHA-256 mismatch.' }
        Expand-Archive -LiteralPath $zip -DestinationPath $toolsFolder -Force
        $Rclone = Join-Path $toolsFolder "rclone-$version-windows-amd64\rclone.exe"
        if (-not (Test-Path -LiteralPath $Rclone)) { throw 'rclone.exe is absent after extraction.' }
    }
    $null = Capture-Rclone @('config','create','nox_server','sftp','host',$ServerHost,'port',"$ServerPort",'user','root','key_file',$SshKeyPath,'known_hosts_file',$KnownHosts,'shell_type','unix')

    if ([string]::IsNullOrEmpty($SessionId)) {
        if (Test-Path -LiteralPath $StateFile) {
            $oldState = [IO.File]::ReadAllText($StateFile) | ConvertFrom-Json
            if ((Get-Field $oldState 'complete' $false) -eq $false) { $SessionId = [string]$oldState.session }
        }
        if ([string]::IsNullOrEmpty($SessionId)) { $SessionId = 'nox-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ') }
    }
    if ($SessionId -notmatch '^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$') { throw 'Invalid persisted session ID.' }
    Write-PlainFile $StateFile (@{session=$SessionId;complete=$false} | ConvertTo-Json)
    $LocalSession = Join-Path (Join-Path $DestinationRoot 'BACKUPS') $SessionId
    $LocalData = Join-Path $LocalSession 'data'
    $null = New-Item -ItemType Directory -Force -Path $LocalData
    $ServerStage = "/root/nox/state/pc_exports/$SessionId"
    Invoke-Ssh 'umask 077; mkdir -p /root/nox/scripts /root/nox/state'
    Copy-ToServer $Helper '/root/nox/scripts/nox_pc_export.py'
    $helperSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $Helper).Hash.ToLowerInvariant()
    Invoke-Ssh "printf '%s  %s\n' '$helperSha' '/root/nox/scripts/nox_pc_export.py' | sha256sum -c -"
    if (Test-Path -LiteralPath $ColdHelper -PathType Leaf) {
        Copy-ToServer $ColdHelper '/root/nox/scripts/nox_cold_drive.py'
        $coldSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $ColdHelper).Hash.ToLowerInvariant()
        Invoke-Ssh "printf '%s  %s\n' '$coldSha' '/root/nox/scripts/nox_cold_drive.py' | sha256sum -c -"
    }
    Invoke-Ssh 'test -f /root/nox/scripts/nox_cold_drive.py'
    Write-Host 'Creating consistent SQLite snapshots and hashing the backup inventory. Training continues.'
    Invoke-Ssh "python3 /root/nox/scripts/nox_pc_export.py plan --session '$SessionId'"
    $ManifestFile = Join-Path $LocalSession 'manifest.json'
    $SelectionFile = Join-Path $LocalSession 'selected.txt'
    Copy-FromServer "$ServerStage/manifest.json" $ManifestFile
    Copy-FromServer "$ServerStage/selected.txt" $SelectionFile
    $manifest = [IO.File]::ReadAllText($ManifestFile) | ConvertFrom-Json
    if ($manifest.schema_version -ne 1 -or $manifest.instance_id -ne 60509551 -or $manifest.session -cne $SessionId) { throw 'Backup manifest identity mismatch.' }
    foreach ($row in $manifest.files) { $null = Relative-Local $row.source_rel $LocalData }
    $driveInfo = New-Object IO.DriveInfo -ArgumentList ([IO.Path]::GetPathRoot($LocalData))
    [long]$already = 0
    foreach ($row in $manifest.files) {
        $p = Relative-Local $row.source_rel $LocalData
        if (Test-Path -LiteralPath $p -PathType Leaf) { $already += [Math]::Min([long](Get-Item -LiteralPath $p).Length, [long]$row.bytes) }
    }
    [long]$PcReserve = [Math]::Max(20GB, [Math]::Ceiling($driveInfo.TotalSize * 0.10))
    if ($driveInfo.AvailableFreeSpace -lt ([long]$manifest.total_bytes - $already + $PcReserve)) { throw 'PC needs enough free space for the complete backup while retaining 20 GiB or 10% of its volume, whichever is larger.' }
    Write-Host ("Copying {0:N1} GiB / {1} files to {2}" -f ($manifest.total_bytes / 1GB), $manifest.files.Count, $LocalData)
    Invoke-Rclone @('copy','nox_server:/root/nox',$LocalData,'--files-from-raw',$SelectionFile,'--immutable','--transfers','4','--checkers','4','--stats','30s','--stats-one-line')
    $verified = New-Object 'System.Collections.Generic.List[object]'
    foreach ($row in $manifest.files) {
        $path = Relative-Local $row.source_rel $LocalData
        if ((Get-Item -LiteralPath $path).Length -ne [long]$row.bytes) { throw "PC size mismatch: $($row.restore_rel)" }
        $digest = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
        if ($digest -cne $row.sha256) { throw "PC SHA-256 mismatch: $($row.restore_rel). No source is deleted. Use a new -SessionId if the live source changed." }
        $verified.Add(@{source_rel=$row.source_rel;bytes=[long]$row.bytes;local_sha256=$digest;drive_sha256=''})
    }
    # Commit PC-only evidence before any Google API/OAuth operation. This receipt
    # cannot enter finalize's distinct two-copy eviction gate.
    $manifestSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $ManifestFile).Hash.ToLowerInvariant()
    $PcReceiptFile = Join-Path $LocalSession 'pc_verified.json'
    $pcReceipt = @{schema='NOX_PC_OVERFLOW_V1';session=$SessionId;manifest_sha256=$manifestSha;
                  pc_backup_root=$DestinationRoot;pc_session_rel="BACKUPS/$SessionId/data";
                  pc_verified=$true;drive_verified=$false;server_sources_retained=$true;
                  verified_at=[DateTime]::UtcNow.ToString('o');files=@($verified)}
    Write-PlainFile $PcReceiptFile ($pcReceipt | ConvertTo-Json -Depth 8)
    Copy-ToServer $PcReceiptFile "$ServerStage/pc_verified.json"
    Invoke-Ssh "python3 /root/nox/scripts/nox_pc_export.py register-pc --session '$SessionId'"
    Copy-FromServer "$ServerStage/pc_result.json" (Join-Path $LocalSession 'pc-server-result.json')
    Write-Host "PC backup passed full SHA-256 verification: $LocalSession"
    $DriveComplete = $false
    $DriveVerified = $false
    $EvictionRequestedOnServer = $false
    $DriveState = 'NOT_REQUESTED'
    if ($StoragePolicy -eq 'PreferDrive') {
      try {
    Initialize-Drive
    $DriveState = 'CHECKING_QUOTA'
    $quota = (Capture-Rclone @('about','nox_drive:','--json')) | ConvertFrom-Json
    $freeBytes = Get-Field $quota 'free' $null
    # An omitted field means unknown/unlimited, never zero. For a resumed
    # session subtract already uploaded expected objects conservatively.
    [long]$uploaded = 0
    try {
        $remoteFiles = (Capture-Rclone @('lsjson',"nox_drive:$SessionId",'--recursive','--files-only')) | ConvertFrom-Json
        $expectedSizes = @{}
        foreach ($row in $manifest.files) { $expectedSizes[[string]$row.source_rel] = [long]$row.bytes }
        foreach ($remoteFile in $remoteFiles) {
            $remotePath = [string](Get-Field $remoteFile 'Path' '')
            if ($expectedSizes.ContainsKey($remotePath)) { $uploaded += [Math]::Min([long]$remoteFile.Size, $expectedSizes[$remotePath]) }
        }
    } catch { $uploaded = 0 }
    [long]$driveNeeded = [Math]::Max(0, [long]$manifest.total_bytes - $uploaded) + 16MB
    if ($null -ne $freeBytes -and [long]$freeBytes -lt $driveNeeded) {
        $DriveState = 'QUOTA_INSUFFICIENT'
        throw 'Drive quota cannot hold this backup; the verified PC overflow copy is retained.'
    }
    $DriveState = 'UPLOADING'
    $DriveSession = "nox_drive:$SessionId"
    Invoke-Rclone @('copy',$LocalData,$DriveSession,'--files-from-raw',$SelectionFile,'--immutable','--transfers','4','--checkers','4','--stats','30s','--stats-one-line','--drive-stop-on-upload-limit','--retries','2','--low-level-retries','3')
    $null = Capture-Rclone @('copyto',$ManifestFile,"$DriveSession/manifest.json",'--immutable')
    $manifestSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $ManifestFile).Hash.ToLowerInvariant()
    if ((Readback-Sha "$DriveSession/manifest.json" (Get-Item -LiteralPath $ManifestFile).Length) -cne $manifestSha) { throw 'Drive manifest SHA-256 mismatch.' }
    $index = 0
    foreach ($row in $manifest.files) {
        $index++
        Write-Host "Drive full SHA-256 readback $index / $($manifest.files.Count): $($row.restore_rel)"
        $digest = Readback-Sha "$DriveSession/$($row.source_rel)" ([long]$row.bytes)
        if ($digest -cne $row.sha256) { throw 'Drive SHA-256 mismatch. No source is deleted.' }
        $verified[$index-1].drive_sha256 = $digest
    }
    $DriveVerified = $true
    $DriveState = 'VERIFIED_FINALIZE_PENDING'
    $receipt = @{schema_version=1;session=$SessionId;manifest_sha256=$manifestSha;all_verified=$true;
                 drive_remote=$DriveSession;verified_at=[DateTime]::UtcNow.ToString('o');files=@($verified)}
    $ReceiptFile = Join-Path $LocalSession 'verified.json'
    Write-PlainFile $ReceiptFile ($receipt | ConvertTo-Json -Depth 8)
    # A resumed verification has a new timestamp. Retain every receipt under
    # its content hash so --immutable never blocks a valid resumed transfer.
    $receiptSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $ReceiptFile).Hash.ToLowerInvariant()
    $null = Capture-Rclone @('copyto',$ReceiptFile,"$DriveSession/verified-$receiptSha.json",'--immutable')
    Copy-ToServer $ReceiptFile "$ServerStage/verified.json"
    # Export only the nox_drive section; no PC SSH key, SFTP remote or other account.
    $privateConfig = [IO.File]::ReadAllText($Config)
    $driveSection = [regex]::Match($privateConfig, '(?ms)^\[nox_drive\]\s*\r?\n(.*?)(?=^\[|\z)')
    if (-not $driveSection.Success) { throw 'Dedicated Drive configuration is missing.' }
    $ServerConfig = Join-Path $Access 'nox-server-drive.conf'
    Write-PlainFile $ServerConfig ($driveSection.Value.Trim() + "`n")
    Invoke-Ssh 'umask 077; touch /root/nox/state/cold_drive.conf.new; chmod 600 /root/nox/state/cold_drive.conf.new'
    Copy-ToServer $ServerConfig '/root/nox/state/cold_drive.conf.new'
    Invoke-Ssh 'chmod 600 /root/nox/state/cold_drive.conf.new && mv /root/nox/state/cold_drive.conf.new /root/nox/state/cold_drive.conf'
    $finalizeCommand = "python3 /root/nox/scripts/nox_pc_export.py finalize --session '$SessionId'"
    if ($EvictInactiveModels) { $finalizeCommand += ' --evict-inactive-gguf'; $EvictionRequestedOnServer = $true }
    Invoke-Ssh $finalizeCommand
    Copy-FromServer "$ServerStage/result.json" (Join-Path $LocalSession 'server-result.json')
    $DriveComplete = $true
    $DriveState = 'VERIFIED_FINALIZED'
    Write-Host "DONE: PC and Drive contents passed full SHA-256 verification. Backup: $LocalSession"
    Write-Host "NOX Drive catalog: /root/nox/state/cold_drive_catalog.json"
    Write-Host 'Use nox_cold_drive.py load with the catalog SHA-256 and RAM admission checks. Loading every model into RAM is not enabled.'
      } catch {
        if ($DriveState -notin @('QUOTA_INSUFFICIENT','VERIFIED_FINALIZE_PENDING')) { $DriveState = 'UNAVAILABLE_OR_INCOMPLETE' }
        if ($EvictionRequestedOnServer) {
            Write-Host 'PC and Drive were verified; server finalization needs receipt inspection. Some explicitly requested inactive GGUF removals may already have completed.'
        } else {
            Write-Host "PC overflow retained; Drive state: $DriveState. No source deletion was requested. Rerun the same session to finish Drive verification."
        }
      }
    }
    Write-PlainFile $StateFile (@{session=$SessionId;complete=($DriveComplete -or $StoragePolicy -eq 'PcOnly');
        pc_verified=$true;drive_verified=$DriveVerified;drive_state=$DriveState;backup=$LocalSession;
        storage_policy=$StoragePolicy;server_sources_retained_on_fallback=(-not $EvictionRequestedOnServer)} | ConvertTo-Json)
    if (-not $DriveComplete) {
        Write-Host 'PC overflow catalog: /root/nox/state/pc_overflow_catalog.json.'
        if (-not $EvictionRequestedOnServer) {
            Write-Host 'Existing server weights and optimizer state remain retained.'
            if ($EvictInactiveModels) { Write-Host 'Inactive-model eviction remains pending the verified PC + Drive pair.' }
        }
    }
    Write-Host ("Resume/control SSH: ssh -i `"{0}`" -p {1} -o StrictHostKeyChecking=yes -o 'UserKnownHostsFile=`"{2}`"' {3}" -f $SshKeyPath,$ServerPort,$KnownHosts.Replace('\','/'),$Target)
} finally {
    $PlainApiKey = $null
    $GoogleSecret = $null
    Remove-Item Env:RCLONE_CONFIG_NOX_DRIVE_CLIENT_ID -ErrorAction SilentlyContinue
    Remove-Item Env:RCLONE_CONFIG_NOX_DRIVE_CLIENT_SECRET -ErrorAction SilentlyContinue
}
