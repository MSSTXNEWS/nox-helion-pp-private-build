#requires -Version 5.1
<#
One-time Windows Administrator bootstrap for the owner's existing NOX instance.
The logon task then reconnects as the same, non-elevated interactive user.
No Windows password is saved. The Vast token is CurrentUser DPAPI ciphertext.
The dedicated server operator PRIVATE key stays on NOX; only its public key is
retrieved. Existing Windows SSH keys, listeners and user rules are preserved.

Install:   .\NOX_CONNECT_PC.ps1
Status:    .\NOX_CONNECT_PC.ps1 -Mode Status
Uninstall: .\NOX_CONNECT_PC.ps1 -Mode Uninstall

Connection is available while this user is logged on, the PC is awake and its
network works. This does not copy weights or make a second verified backup.
#>
[CmdletBinding()]
param(
    [ValidateSet('Install','Connect','Status','Uninstall')][string]$Mode = 'Install',
    [string]$DestinationRoot = 'C:\NOX_HELION',
    [ValidateRange(0,65535)][int]$LocalSshPort = 0,
    [ValidateRange(20,1024)][int]$ReserveGiB = 20,
    [ValidateRange(10,90)][int]$ReservePercent = 10
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$InstanceId = 60509551
$HostPin = 'SHA256:G4hmMllaT4uSfx+Gup9vjSySLXJT1cSc/9XePr7XmGc'
$OperatorPublicSha256 = '79d04e6c4ab99cb56213684706ff58d6e4eac84684d0018534543d6eef8021a7'
$Utf8 = New-Object System.Text.UTF8Encoding -ArgumentList $false
$PlainApiKey = $null
$DestinationRoot = [IO.Path]::GetFullPath($DestinationRoot).TrimEnd('\')
if ($DestinationRoot -notmatch '^[A-Za-z]:\\[^\x00-\x1f"<>|?*:]+$' -or $DestinationRoot -match '(^|\\)\.\.?(\\|$)') {
    throw 'Use a normal absolute local drive folder, for example C:\NOX_HELION.'
}
$LinkRoot = Join-Path $DestinationRoot 'ACCESS\pc-link'
$ManifestFile = Join-Path $LinkRoot 'installation.json'
$StatusFile = Join-Path $LinkRoot 'status.json'
$StopFile = Join-Path $LinkRoot 'STOP'
$KnownHosts = Join-Path $LinkRoot 'known_hosts'
$KeyPath = Join-Path $LinkRoot 'pc_to_nox_ed25519'
$TokenFile = Join-Path $LinkRoot 'vast-api.dpapi'
$RunnerFile = Join-Path $LinkRoot 'NOX_CONNECT_PC.ps1'
$LogFile = Join-Path $LinkRoot 'connection.log'
$SshArguments = @()
$Target = ''
$Manifest = $null

function Get-Field($Object, [string]$Name, $Default = $null) {
    if ($null -eq $Object) { return $Default }
    $p = $Object.PSObject.Properties[$Name]
    if ($null -eq $p) { return $Default }
    return $p.Value
}
function Set-Field($Object, [string]$Name, $Value) {
    $Object | Add-Member -NotePropertyName $Name -NotePropertyValue $Value -Force
}
function Write-PlainFile([string]$Path, [string]$Value) {
    [IO.File]::WriteAllText($Path, $Value, $Utf8)
}
function Write-AtomicJson([string]$Path, $Value) {
    $temp = $Path + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    try {
        Write-PlainFile $temp ($Value | ConvertTo-Json -Depth 12)
        if ([IO.File]::Exists($Path)) { [IO.File]::Replace($temp, $Path, [NullString]::Value) }
        else { [IO.File]::Move($temp, $Path) }
    } finally { if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Force } }
}
function Save-Manifest { Write-AtomicJson $ManifestFile $script:Manifest }
function Protect-Path([string]$Path, [switch]$Directory, [switch]$Administrators) {
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User
    if ($Directory) {
        $null = New-Item -ItemType Directory -Force -Path $Path
        $acl = New-Object Security.AccessControl.DirectorySecurity
        $inherit = [Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit'
    } else {
        $acl = New-Object Security.AccessControl.FileSecurity
        $inherit = [Security.AccessControl.InheritanceFlags]::None
    }
    $acl.SetAccessRuleProtection($true, $false)
    $acl.SetOwner($sid)
    $ids = @($sid, (New-Object Security.Principal.SecurityIdentifier('S-1-5-18')))
    if ($Administrators) { $ids += New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544') }
    foreach ($id in $ids) {
        $rule = New-Object Security.AccessControl.FileSystemAccessRule($id, 'FullControl', $inherit, 'None', 'Allow')
        $acl.AddAccessRule($rule)
    }
    Set-Acl -LiteralPath $Path -AclObject $acl
}
function Windows-PathAncestors([string]$Path) {
    # Keep the drive root absolute. A provider-relative C: can refer to the
    # current directory on that drive; it must never replace C:\ in this check.
    $current = $Path.Replace('/','\')
    if ($current -notmatch '^[A-Za-z]:\\' -or $current -match '(^|\\)\.\.?(\\|$)' -or $current -match '[\x00-\x1f]') {
        throw 'HOLD_NONLOCAL_CHECKED_PATH'
    }
    $root = $current.Substring(0,3)
    $current = $current.TrimEnd('\')
    if ($current.Length -eq 2) { $current = $root }
    while ($true) {
        $current
        if ($current.Equals($root,[StringComparison]::OrdinalIgnoreCase)) { break }
        $slash = $current.LastIndexOf('\')
        if ($slash -le 2) { $current = $root } else { $current = $current.Substring(0,$slash) }
    }
}
function Local-PathAttributes([string]$Path) {
    # Query filesystem attributes directly, without provider/drive aliases.
    # GetAttributes retains ReparsePoint for links; missing nodes are allowed
    # only because their existing parents are still checked below.
    try { return [IO.File]::GetAttributes($Path) }
    catch [IO.FileNotFoundException] { return $null }
    catch [IO.DirectoryNotFoundException] { return $null }
}
function Assert-NoReparse([string]$Path, [ValidatePattern('^[A-Z_]{1,32}$')][string]$Scope = 'LOCAL_PATH') {
    $depth = 0
    foreach ($current in @(Windows-PathAncestors $Path)) {
        $attributes = Local-PathAttributes $current
        if ($null -ne $attributes -and (([long]$attributes -band [long][IO.FileAttributes]::ReparsePoint) -ne 0)) {
            # Local diagnostic only: never sent to NOX, Vast, or connection.log.
            Write-Warning ("NOX path check: scope=$Scope; ancestor=$depth; attributes=$([long]$attributes); path=$current. Existing files were preserved. Select an ordinary local folder with -DestinationRoot.") -WarningAction Continue
            throw ('HOLD_REPARSE_PATH_' + $Scope + '_D' + $depth)
        }
        $depth++
    }
}
function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Open Windows PowerShell as Administrator for Install or Uninstall, using your usual Windows account.'
    }
}
function Unwrap-Secure([Security.SecureString]$Value) {
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}
function Quote-Native([string]$Value) {
    return '"' + ([regex]::Replace([regex]::Replace($Value, '(\\*)"', '$1$1\"'), '(\\+)$', '$1$1')) + '"'
}
function New-Native([string]$Program, [string[]]$Argv, [switch]$Stdin) {
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = $Program
    $info.Arguments = (($Argv | ForEach-Object { Quote-Native $_ }) -join ' ')
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.RedirectStandardInput = [bool]$Stdin
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $info
    $null = $process.Start()
    return $process
}
function Native-Capture([string]$Program, [string[]]$Argv, [string]$InputText = '', [int]$TimeoutSeconds = 60, [switch]$ReturnResult) {
    $process = New-Native $Program $Argv -Stdin
    try {
        $outTask = $process.StandardOutput.ReadToEndAsync()
        $errTask = $process.StandardError.ReadToEndAsync()
        $bytes = $Utf8.GetBytes($InputText)
        $process.StandardInput.BaseStream.Write($bytes, 0, $bytes.Length)
        $process.StandardInput.Close()
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) { throw 'HOLD_COMMAND_TIMEOUT' }
        $output = $outTask.GetAwaiter().GetResult()
        $null = $errTask.GetAwaiter().GetResult()
        if ($ReturnResult) { return [pscustomobject]@{exit_code=$process.ExitCode;stdout=$output} }
        if ($process.ExitCode -ne 0) { throw "HOLD_COMMAND_EXIT_$($process.ExitCode)" }
        return $output
    } finally {
        if (-not $process.HasExited) { $process.Kill(); $process.WaitForExit() }
        $process.Dispose()
    }
}
function Text-Sha256([string]$Text) {
    $hash = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($hash.ComputeHash($Utf8.GetBytes($Text))).Replace('-','').ToLowerInvariant()) }
    finally { $hash.Dispose() }
}
function Public-Identity([string]$Value) {
    if ($Value.Trim() -notmatch '^ssh-ed25519 ([A-Za-z0-9+/=]+)(?: [^\r\n]*)?$') { throw 'HOLD_PUBLIC_KEY_FORMAT' }
    $blob = [Convert]::FromBase64String($Matches[1])
    if ($blob.Length -ne 51 -or [Text.Encoding]::ASCII.GetString($blob,4,11) -cne 'ssh-ed25519' -or $blob[3] -ne 11 -or $blob[18] -ne 32) {
        throw 'HOLD_ED25519_KEY_FORMAT'
    }
    return 'ssh-ed25519 ' + [Convert]::ToBase64String($blob)
}
function Public-Fingerprint([string]$Value) {
    $identity = Public-Identity $Value
    $blob = [Convert]::FromBase64String(($identity -split ' ')[1])
    $hash = [Security.Cryptography.SHA256]::Create()
    try { return 'SHA256:' + [Convert]::ToBase64String($hash.ComputeHash($blob)).TrimEnd('=') }
    finally { $hash.Dispose() }
}
function Write-Event([string]$Code) {
    if ($Code -notmatch '^[A-Z0-9_]{1,100}$') { $Code = 'ERROR_REDACTED' }
    if ((Test-Path -LiteralPath $LogFile) -and (Get-Item -LiteralPath $LogFile).Length -ge 1MB) {
        $last = $LogFile + '.3'
        if (Test-Path -LiteralPath $last) { Remove-Item -LiteralPath $last -Force }
        for ($i = 2; $i -ge 1; $i--) {
            $old = $LogFile + '.' + $i
            if (Test-Path -LiteralPath $old) { Move-Item -LiteralPath $old -Destination ($LogFile + '.' + ($i+1)) -Force }
        }
        Move-Item -LiteralPath $LogFile -Destination ($LogFile + '.1') -Force
    }
    [IO.File]::AppendAllText($LogFile, ([DateTime]::UtcNow.ToString('o') + ' ' + $Code + "`n"), $Utf8)
}
function Write-Status([string]$State, [bool]$Connected = $false) {
    Write-AtomicJson $StatusFile ([ordered]@{
        schema='NOX_PC_LINK_STATUS_V1'; state=$State; connected=$Connected;
        checked_utc=[DateTime]::UtcNow.ToString('o'); instance_id=$InstanceId;
        installation_id=$script:Manifest.installation_id
    })
}
function Vast-Request([string]$Method, [string]$Path, $Payload = $null) {
    $request = @{Method=$Method; Uri=('https://console.vast.ai/api/' + $Path);
        Headers=@{Authorization=('Bearer ' + $script:PlainApiKey);Accept='application/json'};TimeoutSec=45}
    if ($null -ne $Payload) { $request.Body=($Payload | ConvertTo-Json -Compress);$request.ContentType='application/json' }
    try { return Invoke-RestMethod @request }
    catch { throw 'HOLD_VAST_OWNER_API' }
}
function With-ApiToken {
    $secure = ConvertTo-SecureString ([IO.File]::ReadAllText($TokenFile).Trim())
    try { $script:PlainApiKey = Unwrap-Secure $secure }
    finally { $secure.Dispose() }
}
function Find-OwnedKey([string]$PublicKey) {
    $response = Vast-Request 'GET' "v0/instances/$InstanceId/ssh/"
    $keys = Get-Field $response 'ssh_keys' (Get-Field $response 'keys' $response)
    if ($keys -is [string]) { $keys = $keys | ConvertFrom-Json }
    $identity = Public-Identity $PublicKey
    return @($keys | Where-Object {
        $value = [string](Get-Field $_ 'public_key' (Get-Field $_ 'ssh_key' (Get-Field $_ 'key' '')))
        $parts = $value.Trim() -split '\s+'
        $parts.Count -ge 2 -and (($parts[0..1] -join ' ') -ceq $identity)
    })
}
function Refresh-Route([switch]$Attach) {
    With-ApiToken
    try {
        $listing = Vast-Request 'GET' 'v1/instances/?owner=me'
        $instances = Get-Field $listing 'instances' $listing
        $owned = @($instances | Where-Object { [long](Get-Field $_ 'id' -1) -eq $InstanceId })
        if ($owned.Count -ne 1 -or (Get-Field $owned[0] 'actual_status' '') -ne 'running') { throw 'HOLD_OWNED_INSTANCE_NOT_RUNNING' }
        $address = [string](Get-Field $owned[0] 'public_ipaddr' '')
        $ip = $null
        if (-not [Net.IPAddress]::TryParse($address,[ref]$ip) -or $ip.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork) { throw 'HOLD_OWNER_ROUTE' }
        $ports = @(Get-Field (Get-Field $owned[0] 'ports') '22/tcp' @())
        $numbers = @($ports | ForEach-Object { [int](Get-Field $_ 'HostPort' 0) } | Where-Object { $_ -ge 1 -and $_ -le 65535 } | Select-Object -Unique)
        if ($numbers.Count -ne 1) { throw 'HOLD_OWNER_ROUTE' }
        $port = $numbers[0]
        if ($Attach) {
            $public = [IO.File]::ReadAllText($KeyPath + '.pub').Trim()
            $matching = @(Find-OwnedKey $public)
            if ($matching.Count -eq 0) { $null = Vast-Request 'POST' "v0/instances/$InstanceId/ssh/" @{ssh_key=$public} }
        }
    } finally { $script:PlainApiKey = $null }
    $candidate = Native-Capture 'ssh-keyscan.exe' @('-T','15','-p',"$port",'-t','ed25519',$address)
    $lines = @($candidate -split '\r?\n' | Where-Object { $_ -and -not $_.StartsWith('#') })
    if ($lines.Count -ne 1) { throw 'HOLD_HOST_PIN' }
    $parts = $lines[0] -split '\s+'
    if ($parts.Count -ne 3 -or (Public-Fingerprint ($parts[1..2] -join ' ')) -cne $HostPin) { throw 'HOLD_HOST_PIN' }
    # Use a deterministic known_hosts name instead of trusting keyscan's first field.
    Write-PlainFile $KnownHosts ("[$address]:$port " + ($parts[1..2] -join ' ') + "`n" + "$address " + ($parts[1..2] -join ' ') + "`n")
    $script:Target = "root@$address"
    $script:SshArguments = @('-F','NUL','-i',$KeyPath,'-p',"$port",'-o','IdentitiesOnly=yes',
        '-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','HostKeyAlgorithms=ssh-ed25519',
        '-o',('UserKnownHostsFile="' + $KnownHosts.Replace('\','/') + '"'),'-o','GlobalKnownHostsFile=NUL',
        '-o','ConnectTimeout=20','-o','LogLevel=ERROR')
}

# Only this fixed, reviewable Python program runs on NOX. Personal metadata is
# supplied through stdin, never a shell command line, task argument or log.
$RemoteControl = @'
import base64, datetime, fcntl, hashlib, ipaddress, json, os, re, socket, stat, struct, subprocess, sys, tempfile
from pathlib import Path
STATE = Path('/root/nox/state/pc_shell')
CONNECTION = STATE / 'connection.json'

def fail(code):
    raise RuntimeError(code)

def public_key(value):
    if not isinstance(value, str) or not re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/=]+', value):
        fail('HOLD_PUBLIC_KEY_FORMAT')
    blob = base64.b64decode(value.split()[1], validate=True)
    if len(blob) != 51 or blob[:4] != b'\0\0\0\x0b' or blob[4:15] != b'ssh-ed25519' or blob[15:19] != b'\0\0\0 ': 
        fail('HOLD_PUBLIC_KEY_FORMAT')
    return 'SHA256:' + base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip('=')

def validate(data):
    if not isinstance(data, dict) or data.get('schema') != 'NOX_PC_LINK_V1' or data.get('instance_id') != 60509551:
        fail('HOLD_CONNECTION_SCHEMA')
    if data.get('reverse_host') != '127.0.0.1' or data.get('reverse_port') != 46051:
        fail('HOLD_REVERSE_BIND')
    if type(data.get('pc_ssh_port')) is not int or not 1 <= data['pc_ssh_port'] <= 65535:
        fail('HOLD_PC_PORT')
    if not isinstance(data.get('pc_user'), str) or not re.fullmatch(r'[A-Za-z0-9_.@\\ -]{1,128}', data['pc_user']) or data['pc_user'].startswith('-'):
        fail('HOLD_PC_USER')
    root = data.get('backup_root', '')
    if not isinstance(root, str) or not re.fullmatch(r'[A-Za-z]:\\[^\x00-\x1f"<>|?*:]+', root) or any(x in ('.','..') for x in root[3:].split('\\')):
        fail('HOLD_BACKUP_ROOT')
    if not re.fullmatch(r'[a-f0-9]{32}', str(data.get('installation_id',''))): fail('HOLD_INSTALLATION_ID')
    if public_key(data.get('pc_host_key')) != data.get('pc_host_key_sha256'): fail('HOLD_PC_HOST_PIN')
    if not re.fullmatch(r'SHA256:[A-Za-z0-9+/]{43}', str(data.get('pc_key_fingerprint',''))): fail('HOLD_PC_KEY_FINGERPRINT')
    if type(data.get('reserve_bytes')) is not int or data['reserve_bytes'] < 20*1024**3: fail('HOLD_RESERVE')
    if type(data.get('reserve_percent')) is not int or not 10 <= data['reserve_percent'] <= 90: fail('HOLD_RESERVE')
    return data

def atomic(path, text):
    if path.is_symlink(): fail('HOLD_STATE_SYMLINK')
    fd, name = tempfile.mkstemp(prefix='pc-link-', dir=str(STATE))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as out:
            out.write(text); out.flush(); os.fsync(out.fileno())
        os.replace(name, path)
        dfd = os.open(str(STATE), os.O_DIRECTORY)
        try: os.fsync(dfd)
        finally: os.close(dfd)
    finally:
        if os.path.exists(name): os.unlink(name)

def existing(installation_id):
    if CONNECTION.is_symlink(): fail('HOLD_STATE_SYMLINK')
    if CONNECTION.exists():
        prior = json.loads(CONNECTION.read_text())
        if prior.get('installation_id') != installation_id: fail('HOLD_OTHER_PC_REGISTRATION')
        return prior
    return None

def forwarding():
    fields = os.environ.get('SSH_CONNECTION','').split()
    if len(fields) != 4: fail('HOLD_SSH_CONNECTION')
    peer, _, local, port = fields
    ipaddress.ip_address(peer); ipaddress.ip_address(local)
    # With UseDNS=no sshd matches Host against the numeric peer. If DNS is used,
    # require forward-confirmed reverse DNS, exactly as OpenSSH's peer lookup.
    base = subprocess.run(['/usr/sbin/sshd','-T'], capture_output=True, text=True, timeout=8)
    if base.returncode: fail('HOLD_SSHD_CONFIG')
    global_values = dict(x.split(None,1) for x in base.stdout.splitlines() if ' ' in x)
    host = peer
    if global_values.get('usedns') == 'yes':
        try:
            candidate = socket.gethostbyaddr(peer)[0].lower()
            addresses = {x[4][0] for x in socket.getaddrinfo(candidate,None)}
            if peer in addresses: host = candidate
        except OSError: pass
    match = 'user=root,addr=%s,host=%s,laddr=%s,lport=%s' % (peer,host,local,port)
    result = subprocess.run(['/usr/sbin/sshd','-T','-C',match],capture_output=True,text=True,timeout=8)
    if result.returncode: fail('HOLD_SSHD_CONFIG')
    values = dict(x.split(None,1) for x in result.stdout.splitlines() if ' ' in x)
    if values.get('disableforwarding') == 'yes' or values.get('allowtcpforwarding') not in ('yes','remote','all'):
        fail('HOLD_FORWARDING_DISABLED')
    if values.get('gatewayports') not in ('no','clientspecified'): fail('HOLD_PUBLIC_REVERSE_LISTENER')
    return True

def listener():
    addresses = []
    for name in ('tcp','tcp6'):
        for line in Path('/proc/net/' + name).read_text().splitlines()[1:]:
            columns = line.split()
            address, port = columns[1].split(':')
            if columns[3] != '0A' or int(port,16) != 46051: continue
            if name == 'tcp': value = socket.inet_ntop(socket.AF_INET,struct.pack('<I',int(address,16)))
            else:
                packed = b''.join(struct.pack('<I',int(address[i:i+8],16)) for i in range(0,32,8))
                value = socket.inet_ntop(socket.AF_INET6,packed)
            addresses.append(value)
    if addresses != ['127.0.0.1']: fail('HOLD_REVERSE_LISTENER_NOT_EXCLUSIVE_LOOPBACK')

def verify(data):
    listener()
    key = STATE / 'operator_ed25519'
    if key.is_symlink() or not key.is_file() or stat.S_IMODE(key.stat().st_mode) != 0o600: fail('HOLD_OPERATOR_KEY')
    known = STATE / 'bootstrap_known_hosts'
    atomic(known, '[127.0.0.1]:46051 ' + data['pc_host_key'] + '\n')
    argv = ['ssh','-F','/dev/null','-i',str(key),'-p','46051','-l',data['pc_user'],
            '-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
            '-o','HostKeyAlgorithms=ssh-ed25519','-o','GlobalKnownHostsFile=/dev/null',
            '-o','UserKnownHostsFile='+str(known),'-o','ConnectTimeout=12','-o','LogLevel=ERROR',
            '127.0.0.1','cmd.exe /d /c echo NOX_PC_LINK_OK']
    result = subprocess.run(argv,capture_output=True,text=True,timeout=20)
    if result.returncode or result.stdout.strip() != 'NOX_PC_LINK_OK': fail('HOLD_PC_SSH_VERIFICATION')

def main():
    if STATE.is_symlink() or not STATE.is_dir() or stat.S_IMODE(STATE.stat().st_mode) != 0o700: fail('HOLD_SERVER_PREPARATION')
    raw = sys.stdin.buffer.read(16385)
    if len(raw) > 16384: fail('HOLD_INPUT_LIMIT')
    request = json.loads(raw)
    action = request.get('action')
    data = validate(request.get('connection'))
    lock = os.open(str(STATE/'connection.lock'),os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        prior = existing(data['installation_id'])
        if action == 'preflight':
            forwarding()
            print(json.dumps({'state':'FORWARDING_ALLOWED'}))
        elif action == 'publish':
            forwarding(); verify(data)
            data['connected_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            data['connected'] = True
            atomic(CONNECTION,json.dumps(data,ensure_ascii=False,indent=2)+'\n')
            helper = Path('/root/nox/scripts/nox_cold_drive.py')
            storage = 'HELPER_NOT_INSTALLED'
            if helper.is_file() and not helper.is_symlink():
                result = subprocess.run(['python3',str(helper),'configure-pc'],capture_output=True,text=True,timeout=20)
                storage = 'CONFIGURED' if result.returncode == 0 else 'CONFIGURATION_PENDING'
                config = STATE.parent/'cold_pc.conf'
                if result.returncode == 0 and config.is_file() and not config.is_symlink():
                    data['owned_cold_pc_config_sha256'] = hashlib.sha256(config.read_bytes()).hexdigest()
                    atomic(CONNECTION,json.dumps(data,ensure_ascii=False,indent=2)+'\n')
            print(json.dumps({'state':'CONNECTED_VERIFIED','storage':storage}))
        elif action == 'verify':
            if prior is None: fail('HOLD_PC_NOT_REGISTERED')
            for field in ('schema','instance_id','reverse_host','reverse_port','pc_ssh_port',
                          'pc_user','pc_host_key','pc_host_key_sha256','backup_root','pc_key_fingerprint'):
                if prior.get(field) != data.get(field): fail('HOLD_LINK_CONFIG_CHANGED')
            forwarding(); verify(data)
            prior['connected'] = True
            prior['connected_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            prior['last_verified_utc'] = prior['connected_utc']
            atomic(CONNECTION,json.dumps(prior,ensure_ascii=False,indent=2)+'\n')
            print(json.dumps({'state':'CONNECTED_VERIFIED'}))
        elif action == 'disconnect':
            if prior:
                prior['connected'] = False
                prior['disconnected_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                atomic(CONNECTION,json.dumps(prior,ensure_ascii=False,indent=2)+'\n')
            print(json.dumps({'state':'DISCONNECTED'}))
        elif action == 'unregister':
            if prior:
                for name in ('bootstrap_known_hosts','rclone_known_hosts'):
                    path = STATE/name
                    if path.is_file() and not path.is_symlink(): path.unlink()
                config = STATE.parent/'cold_pc.conf'
                if config.is_file() and not config.is_symlink():
                    digest = hashlib.sha256(config.read_bytes()).hexdigest()
                    if digest == prior.get('owned_cold_pc_config_sha256'): config.unlink()
                CONNECTION.unlink()
            print(json.dumps({'state':'UNREGISTERED'}))
        else: fail('HOLD_ACTION')
    finally: os.close(lock)

if __name__ == '__main__':
    try: main()
    except Exception as exc:
        message = str(exc)
        print(json.dumps({'state':message if re.fullmatch('HOLD_[A-Z_]+',message) else 'HOLD_REMOTE_CHECK'}))
        raise SystemExit(2)
'@

function Connection-Data {
    return [ordered]@{
        schema='NOX_PC_LINK_V1'; instance_id=$InstanceId; reverse_host='127.0.0.1';reverse_port=46051;
        pc_ssh_port=[int]$script:Manifest.pc_ssh_port; pc_user=[string]$script:Manifest.pc_user;
        pc_host_key=[string]$script:Manifest.pc_host_key;pc_host_key_sha256=[string]$script:Manifest.pc_host_key_sha256;
        backup_root=$DestinationRoot; connected_utc=$null;
        pc_key_fingerprint=[string]$script:Manifest.pc_key_fingerprint;
        installation_id=[string]$script:Manifest.installation_id;
        reserve_bytes=[long]$script:Manifest.reserve_bytes;reserve_percent=[int]$script:Manifest.reserve_percent
    }
}
function Invoke-Remote([string]$Action) {
    $source = [Convert]::ToBase64String($Utf8.GetBytes($RemoteControl))
    $command = 'python3 -c ''import base64;exec(base64.b64decode("' + $source + '"))'''
    $payload = @{action=$Action;connection=(Connection-Data)} | ConvertTo-Json -Compress -Depth 6
    $result = Native-Capture 'ssh.exe' ($script:SshArguments + @($script:Target,$command)) $payload 65 -ReturnResult
    $value = $null
    try { $value = $result.stdout | ConvertFrom-Json } catch { }
    if ($result.exit_code -ne 0) {
        $code = [string](Get-Field $value 'state' '')
        if ($code -match '^HOLD_[A-Z_]+$') { throw $code }
        throw ('HOLD_SSH_EXIT_' + $result.exit_code)
    }
    if ($null -eq $value) { throw 'HOLD_REMOTE_RECEIPT' }
    return $value
}
function Read-Manifest {
    if (-not (Test-Path -LiteralPath $ManifestFile -PathType Leaf)) { throw 'HOLD_INSTALL_FIRST' }
    Assert-NoReparse $ManifestFile 'INSTALLATION_MANIFEST'
    $value = [IO.File]::ReadAllText($ManifestFile) | ConvertFrom-Json
    if ($value.schema -ne 'NOX_PC_INSTALL_V1' -or $value.instance_id -ne $InstanceId -or
        $value.installation_id -notmatch '^[a-f0-9]{32}$' -or $value.owner_sid -ne [Security.Principal.WindowsIdentity]::GetCurrent().User.Value -or
        $value.destination_root -cne $DestinationRoot) { throw 'HOLD_INSTALLATION_IDENTITY' }
    return $value
}
function Sshd-Info {
    $service = Get-CimInstance Win32_Service -Filter "Name='sshd'" -ErrorAction SilentlyContinue
    if ($null -eq $service) { return $null }
    # SCM service commands are parsed with Windows' own argv rules, not eval.
    if (-not ('NoxPcArgv' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class NoxPcArgv {
  [DllImport("shell32.dll", SetLastError=true)] static extern IntPtr CommandLineToArgvW([MarshalAs(UnmanagedType.LPWStr)] string s, out int n);
  [DllImport("kernel32.dll")] static extern IntPtr LocalFree(IntPtr p);
  public static string[] Parse(string s) {
    int n; IntPtr p=CommandLineToArgvW(s,out n);
    if(p==IntPtr.Zero) throw new InvalidOperationException("argv");
    try { var a=new string[n]; for(int i=0;i<n;i++) a[i]=Marshal.PtrToStringUni(Marshal.ReadIntPtr(p,i*IntPtr.Size)); return a; }
    finally { LocalFree(p); }
  }
}
'@
    }
    $parts = [NoxPcArgv]::Parse([string]$service.PathName)
    if ($parts.Count -lt 1 -or [IO.Path]::GetFileName($parts[0]) -ine 'sshd.exe' -or -not (Test-Path -LiteralPath $parts[0] -PathType Leaf)) { throw 'HOLD_SSHD_SERVICE_COMMAND' }
    $config = Join-Path $env:ProgramData 'ssh\sshd_config'
    for ($i = 1; $i -lt $parts.Count; $i++) {
        if ($parts[$i] -eq '-f' -and ($i+1) -lt $parts.Count) { $i++;$config=$parts[$i] }
        elseif ($parts[$i] -notin @('-D','-e')) { throw 'HOLD_CUSTOM_SSHD_OPTIONS' }
    }
    return [pscustomobject]@{exe=$parts[0];config=[IO.Path]::GetFullPath($config);service=$service}
}
function Effective-Sshd($Info, [string]$User, [int]$Port) {
    $context = "user=$User,host=localhost,addr=127.0.0.1,laddr=127.0.0.1,lport=$Port"
    return Native-Capture $Info.exe @('-T','-f',$Info.config,'-C',$context)
}
function Assert-LocalListener($Info, [int]$Port, [bool]$NewService) {
    $service = Get-CimInstance Win32_Service -Filter "Name='sshd'"
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
    $matching = @($listeners | Where-Object { $_.LocalAddress -in @('127.0.0.1','0.0.0.0','::') -and $_.OwningProcess -eq $service.ProcessId })
    if ($service.State -ne 'Running' -or $matching.Count -eq 0) { throw 'HOLD_LOCAL_SSH_LISTENER' }
    if ($NewService) {
        $allOwned = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -eq $service.ProcessId })
        if (@($allOwned | Where-Object { $_.LocalAddress -ne '127.0.0.1' }).Count -gt 0) { throw 'HOLD_LOCAL_PUBLIC_LISTENER' }
    }
}
function Current-SshUser {
    $name = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    $pieces = $name -split '\\',2
    if ($pieces.Count -eq 2 -and $pieces[0] -ieq $env:COMPUTERNAME) { $name = $pieces[1] }
    $name = $name.ToLowerInvariant()
    if ($name -notmatch '^[A-Za-z0-9_.@\\ -]{1,128}$' -or $name.StartsWith('-')) { throw 'HOLD_WINDOWS_LOGIN_FORMAT' }
    return $name
}
function Existing-KeyArguments([string]$Effective, [string]$ProgramDataRoot = $env:ProgramData) {
    if ([string]::IsNullOrWhiteSpace($Effective) -or $Effective -eq 'none') { return '' }
    if ($Effective -match '[\r\n"]') { throw 'HOLD_AMBIGUOUS_AUTHORIZED_KEYS_FILES' }
    $files = @($Effective -split '\s+')
    # sshd -T prints an array separated by spaces without preserving quotation.
    # A custom "C:/keys/team one.pub" is indistinguishable from two filenames.
    # Preserve such configurations by stopping before changing their access.
    $standard = @('.ssh/authorized_keys','.ssh/authorized_keys2',
        '__programdata__/ssh/administrators_authorized_keys',
        ($ProgramDataRoot.Replace('\','/').TrimEnd('/') + '/ssh/administrators_authorized_keys').ToLowerInvariant())
    if ($files.Count -gt 1) {
        foreach ($file in $files) {
            if ($standard -notcontains $file.Replace('\','/').ToLowerInvariant()) { throw 'HOLD_AMBIGUOUS_AUTHORIZED_KEYS_FILES' }
        }
    }
    return (($files | ForEach-Object { '"' + $_.Replace('\','/') + '"' }) -join ' ')
}
function Install-LocalSsh([string]$OperatorKey) {
    $info = Sshd-Info
    $hadService = $null -ne $info
    $originalConfigPath = Join-Path $env:ProgramData 'ssh\sshd_config'
    if ($hadService) { $originalConfigPath=$info.config }
    $initialConfigExisted = Test-Path -LiteralPath $originalConfigPath -PathType Leaf
    if (-not $hadService -and $initialConfigExisted) { throw 'HOLD_PREEXISTING_SSH_CONFIG_WITHOUT_SERVICE' }
    if (-not $hadService) {
        $capability = Get-WindowsCapability -Online -Name 'OpenSSH.Server~~~~0.0.1.0'
        if ($capability.State -ne 'Installed') {
            $null = Add-WindowsCapability -Online -Name 'OpenSSH.Server~~~~0.0.1.0'
            Set-Field $script:Manifest 'installed_server_capability' $true
            Save-Manifest
        }
        $info = Sshd-Info
        if ($null -eq $info) { throw 'HOLD_OPENSSH_SERVER_SERVICE' }
    }
    $existingConfig = $initialConfigExisted
    $newService = -not $initialConfigExisted
    if ($newService -and $info.service.State -eq 'Running') { throw 'HOLD_RUNNING_SSHD_CONFIG_MISSING' }
    Assert-NoReparse $info.config 'SSH_CONFIGURATION'
    $priorText = ''
    if ($existingConfig) { $priorText = [IO.File]::ReadAllText($info.config) }
    $user = Current-SshUser
    $port = $LocalSshPort
    if ($newService) {
        if ($port -eq 0) { $port = 2222 }
        $probe = New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback,$port)
        try { $probe.Start() } finally { $probe.Stop() }
        $folder = Split-Path -Parent $info.config
        $null = New-Item -ItemType Directory -Force -Path $folder
        $null = Native-Capture 'ssh-keygen.exe' @('-A')
        $subsystem = (Join-Path (Split-Path -Parent $info.exe) 'sftp-server.exe').Replace('\','/')
        $priorText = "Port $port`nListenAddress 127.0.0.1`nPubkeyAuthentication yes`nPasswordAuthentication no`nAllowUsers `"$user`"`nSubsystem sftp `"$subsystem`"`n"
        Write-PlainFile $info.config $priorText
        Protect-Path $info.config -Administrators
    }
    if ($port -eq 0) {
        $global = Native-Capture $info.exe @('-T','-f',$info.config)
        $ports = @([regex]::Matches($global,'(?m)^port (\d+)\s*$') | ForEach-Object { [int]$_.Groups[1].Value } | Select-Object -Unique)
        if ($ports.Count -ne 1) { throw 'HOLD_SELECT_LOCAL_SSH_PORT' }
        $port = $ports[0]
    }
    $effective = Effective-Sshd $info $user $port
    $authMatch = [regex]::Match($effective,'(?m)^authorizedkeysfile (.+)\r?$')
    if (-not $authMatch.Success) { throw 'HOLD_AUTHORIZED_KEYS_POLICY' }
    $previousFiles = $authMatch.Groups[1].Value.Trim()
    if ($previousFiles -eq 'none') { $previousFiles = '' }
    $previousArguments = Existing-KeyArguments $previousFiles
    $authFile = Join-Path $env:ProgramData ('ssh\nox_pc_' + $script:Manifest.installation_id + '_authorized_keys')
    Assert-NoReparse $authFile 'AUTHORIZED_KEY'
    if (Test-Path -LiteralPath $authFile) { throw 'HOLD_OWNED_KEY_FILE_EXISTS' }
    $null = New-Item -ItemType Directory -Force -Path (Split-Path -Parent $authFile)
    $authorizedLine = 'from="127.0.0.1,::1",no-agent-forwarding,no-port-forwarding,no-X11-forwarding ' + (Public-Identity $OperatorKey) + ' NOX-PC-' + $script:Manifest.installation_id + "`n"
    Write-PlainFile $authFile $authorizedLine
    Protect-Path $authFile -Administrators
    $marker = 'NOX_PC_LINK_' + $script:Manifest.installation_id
    $keyPathConfig = $authFile.Replace('\','/')
    $block = "`n# BEGIN $marker`nMatch User `"$user`" Address 127.0.0.1,::1`n    AuthorizedKeysFile `"$keyPathConfig`" $previousArguments`nMatch all`n# END $marker`n"
    $firstMatch = [regex]::Match($priorText,'(?im)^\s*Match\s+')
    $insertAt = $priorText.Length
    if ($firstMatch.Success) { $insertAt = $firstMatch.Index }
    $updated = $priorText.Insert($insertAt,$block)
    $backup = Join-Path $LinkRoot 'sshd_config.before'
    if ($existingConfig) { [IO.File]::WriteAllBytes($backup,[IO.File]::ReadAllBytes($info.config)) }
    Set-Field $script:Manifest 'sshd_config' $info.config
    Set-Field $script:Manifest 'sshd_exe' $info.exe
    Set-Field $script:Manifest 'sshd_new' $newService
    Set-Field $script:Manifest 'sshd_prior_state' ([string]$info.service.State)
    Set-Field $script:Manifest 'sshd_prior_start_mode' ([string]$info.service.StartMode)
    Set-Field $script:Manifest 'sshd_owned_block' $block
    Set-Field $script:Manifest 'sshd_owned_config_sha256' (Text-Sha256 $updated)
    Set-Field $script:Manifest 'authorized_file' $authFile
    Set-Field $script:Manifest 'authorized_sha256' (Text-Sha256 $authorizedLine)
    Set-Field $script:Manifest 'pc_user' $user
    Set-Field $script:Manifest 'pc_ssh_port' $port
    Set-Field $script:Manifest 'phase' 'SSH_CONFIG_PREPARED'
    Save-Manifest
    $changed = $false
    try {
        Write-PlainFile $info.config $updated
        $changed = $true
        $null = Native-Capture $info.exe @('-t','-f',$info.config)
        $after = Effective-Sshd $info $user $port
        $afterFiles = [regex]::Match($after,'(?m)^authorizedkeysfile (.+)\r?$').Groups[1].Value.Trim()
        if (-not $afterFiles.Replace('\','/').Contains($keyPathConfig) -or ($previousFiles -and -not $afterFiles.Replace('\','/').EndsWith($previousFiles.Replace('\','/')))) {
            throw 'HOLD_AUTHORIZED_KEYS_PRECEDENCE'
        }
        if ($after -notmatch '(?m)^pubkeyauthentication yes\s*$') { throw 'HOLD_PUBLIC_KEY_AUTH_DISABLED' }
        # Only StartupType/status are changed; the existing service command stays.
        Set-Service -Name sshd -StartupType Automatic
        if ((Get-Service sshd).Status -eq 'Running') { Restart-Service -Name sshd }
        else { Start-Service -Name sshd }
        $deadline = [DateTime]::UtcNow.AddSeconds(15)
        do {
            try { Assert-LocalListener $info $port $newService;break }
            catch { if ([DateTime]::UtcNow -ge $deadline) { throw };Start-Sleep -Milliseconds 300 }
        } while ($true)
        $scan = Native-Capture 'ssh-keyscan.exe' @('-T','5','-p',"$port",'-t','ed25519','127.0.0.1')
        $lines = @($scan -split '\r?\n' | Where-Object { $_ -and -not $_.StartsWith('#') })
        if ($lines.Count -ne 1) { throw 'HOLD_PC_HOST_KEY' }
        $fields = $lines[0] -split '\s+'
        if ($fields.Count -ne 3) { throw 'HOLD_PC_HOST_KEY' }
        $hostKey = Public-Identity ($fields[1..2] -join ' ')
        Set-Field $script:Manifest 'pc_host_key' $hostKey
        Set-Field $script:Manifest 'pc_host_key_sha256' (Public-Fingerprint $hostKey)
        Set-Field $script:Manifest 'phase' 'SSH_READY'
        Save-Manifest
    } catch {
        if ($changed) {
            if ($existingConfig) { [IO.File]::WriteAllBytes($info.config,[IO.File]::ReadAllBytes($backup)) }
            else { Write-PlainFile $info.config $priorText }
            if ($info.service.State -eq 'Running') { Restart-Service -Name sshd -ErrorAction SilentlyContinue }
            else { Stop-Service -Name sshd -ErrorAction SilentlyContinue }
            $start = @{Auto='Automatic';Manual='Manual';Disabled='Disabled'}[[string]$info.service.StartMode]
            if ($start) { Set-Service -Name sshd -StartupType $start -ErrorAction SilentlyContinue }
        }
        throw
    }
}
function Register-LinkTask {
    $taskName = 'NOX-PC-Link-' + $script:Manifest.installation_id
    $powershell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $taskArgs = @('-NoLogo','-NoProfile','-NonInteractive','-WindowStyle','Hidden','-ExecutionPolicy','RemoteSigned',
        '-File',$RunnerFile,'-Mode','Connect','-DestinationRoot',$DestinationRoot)
    $argument = ($taskArgs | ForEach-Object { Quote-Native $_ }) -join ' '
    $old = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($old -and ($old.Actions.Count -ne 1 -or $old.Actions[0].Execute -ine $powershell -or $old.Actions[0].Arguments -cne $argument)) { throw 'HOLD_TASK_OWNERSHIP' }
    Write-PlainFile $RunnerFile ([IO.File]::ReadAllText($PSCommandPath))
    $action = New-ScheduledTaskAction -Execute $powershell -Argument $argument -WorkingDirectory $LinkRoot
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $script:Manifest.owner_sid
    $principal = New-ScheduledTaskPrincipal -UserId $script:Manifest.owner_sid -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    Set-Field $script:Manifest 'task_name' $taskName
    Set-Field $script:Manifest 'task_executable' $powershell
    Set-Field $script:Manifest 'task_arguments' $argument
    Set-Field $script:Manifest 'phase' 'TASK_PREPARED'
    Save-Manifest
    $null = Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description ('NOX owned PC link ' + $script:Manifest.installation_id) -Force
    Set-Field $script:Manifest 'phase' 'INSTALLED'
    Set-Field $script:Manifest 'connection_may_exist' $true
    Save-Manifest
    if (Test-Path -LiteralPath $StopFile) { Remove-Item -LiteralPath $StopFile -Force }
    Write-Status 'INSTALLED_AWAITING_FIRST_CONNECTION'
    Start-ScheduledTask -TaskName $taskName
}
function Run-Connection {
    $script:Manifest = Read-Manifest
    if ($script:Manifest.phase -ne 'INSTALLED') { throw 'HOLD_INCOMPLETE_INSTALLATION' }
    $lock = $null
    try { $lock = [IO.File]::Open((Join-Path $LinkRoot 'runner.lock'),'OpenOrCreate','ReadWrite','None') }
    catch { throw 'HOLD_CONNECTION_ALREADY_RUNNING' }
    $backoff = 5
    try {
        while (-not (Test-Path -LiteralPath $StopFile)) {
            $tunnel = $null
            try {
                Write-Status 'CONNECTING'
                Refresh-Route
                $info = Sshd-Info
                Assert-LocalListener $info ([int]$script:Manifest.pc_ssh_port) ([bool]$script:Manifest.sshd_new)
                $null = Invoke-Remote 'preflight'
                $forward = '127.0.0.1:46051:127.0.0.1:' + [string]$script:Manifest.pc_ssh_port
                $tunnel = New-Native 'ssh.exe' ($script:SshArguments + @('-N','-T','-o','ExitOnForwardFailure=yes',
                    '-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3','-R',$forward,$script:Target))
                $outTask = $tunnel.StandardOutput.ReadToEndAsync()
                $errTask = $tunnel.StandardError.ReadToEndAsync()
                Write-AtomicJson (Join-Path $LinkRoot 'tunnel-process.json') ([ordered]@{
                    pid=$tunnel.Id;started_ticks=$tunnel.StartTime.ToUniversalTime().Ticks;
                    installation_id=$script:Manifest.installation_id
                })
                $deadline = [DateTime]::UtcNow.AddSeconds(45)
                do {
                    if ($tunnel.HasExited) { throw 'HOLD_TUNNEL_EXITED' }
                    try {
                        $receipt = Invoke-Remote 'publish'
                        if ($receipt.state -ne 'CONNECTED_VERIFIED') { throw 'HOLD_PC_VERIFICATION' }
                        break
                    } catch { if ([DateTime]::UtcNow -ge $deadline) { throw };Start-Sleep -Seconds 2 }
                } while ($true)
                Write-Status 'CONNECTED_VERIFIED' $true
                Write-Event 'CONNECTED_VERIFIED'
                $backoff = 5
                $nextVerify = [DateTime]::UtcNow.AddSeconds(60)
                while (-not $tunnel.HasExited -and -not (Test-Path -LiteralPath $StopFile)) {
                    Start-Sleep -Seconds 1
                    if ([DateTime]::UtcNow -ge $nextVerify) {
                        $receipt = Invoke-Remote 'verify'
                        if ($receipt.state -ne 'CONNECTED_VERIFIED') { throw 'HOLD_PC_VERIFICATION' }
                        Write-Status 'CONNECTED_VERIFIED' $true
                        $nextVerify = [DateTime]::UtcNow.AddSeconds(60)
                    }
                }
                if (-not (Test-Path -LiteralPath $StopFile)) { throw 'HOLD_TUNNEL_EXITED' }
            } catch {
                $code = [string]$_.Exception.Message
                if ($code -notmatch '^HOLD_[A-Z0-9_]+$') { $code = 'HOLD_CONNECTION_RETRY' }
                Write-Status $code
                Write-Event $code
            } finally {
                if ($null -ne $tunnel) {
                    if (-not $tunnel.HasExited) { $tunnel.Kill();$tunnel.WaitForExit() }
                    $tunnel.Dispose()
                }
                try { $null = Invoke-Remote 'disconnect' } catch { }
                $processFile = Join-Path $LinkRoot 'tunnel-process.json'
                if (Test-Path -LiteralPath $processFile) { Remove-Item -LiteralPath $processFile -Force }
            }
            for ($i = 0; $i -lt $backoff -and -not (Test-Path -LiteralPath $StopFile); $i++) { Start-Sleep -Seconds 1 }
            $backoff = [Math]::Min(60,$backoff*2)
        }
        Write-Status 'STOPPED'
    } finally { $script:PlainApiKey=$null;if ($null -ne $lock) { $lock.Dispose() } }
}
function Remove-Link {
    $script:Manifest = Read-Manifest
    Write-PlainFile $StopFile 'owner uninstall'
    $taskName = [string](Get-Field $script:Manifest 'task_name' '')
    if ($taskName) {
        $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if ($task) {
            if ($task.Actions.Count -ne 1 -or $task.Actions[0].Execute -ine $script:Manifest.task_executable -or $task.Actions[0].Arguments -cne $script:Manifest.task_arguments) { throw 'HOLD_TASK_CHANGED' }
            Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
            Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        }
    }
    # Only a recorded child with the same PID, start time and dedicated identity
    # may be stopped. Never kill all ssh.exe or any unknown listener.
    $processFile = Join-Path $LinkRoot 'tunnel-process.json'
    if (Test-Path -LiteralPath $processFile) {
        $record = [IO.File]::ReadAllText($processFile) | ConvertFrom-Json
        $process = Get-Process -Id ([int]$record.pid) -ErrorAction SilentlyContinue
        if ($process -and $record.installation_id -eq $script:Manifest.installation_id -and $process.StartTime.ToUniversalTime().Ticks -eq [long]$record.started_ticks) {
            $details = Get-CimInstance Win32_Process -Filter ('ProcessId=' + [int]$record.pid)
            if ($process.ProcessName -ieq 'ssh' -and $details.CommandLine.Contains($KeyPath) -and $details.CommandLine.Contains('127.0.0.1:46051:127.0.0.1:')) { Stop-Process -Id $process.Id }
        }
    }
    $remoteRemoved = -not [bool](Get-Field $script:Manifest 'connection_may_exist' $false)
    if (-not $remoteRemoved) {
        try {
            Refresh-Route;$null=Invoke-Remote 'unregister';$remoteRemoved=$true
            Set-Field $script:Manifest 'connection_may_exist' $false
            Save-Manifest
        } catch { Write-Host 'Server registration cleanup is pending; the local operator key will still be disabled.' }
    }
    $detached = -not [bool](Get-Field $script:Manifest 'key_attach_attempted' $false)
    # Keep the dedicated outgoing key until server metadata has been removed, so
    # an offline uninstall can finish later without another credential bootstrap.
    if ($remoteRemoved -and -not $detached) {
        try {
            With-ApiToken
            $keys = @(Find-OwnedKey ([IO.File]::ReadAllText($KeyPath+'.pub')))
            foreach ($key in $keys) {
                $id = [string](Get-Field $key 'id' '')
                if ($id -notmatch '^\d+$') { throw 'HOLD_KEY_ID' }
                $null = Vast-Request 'DELETE' "v0/instances/$InstanceId/ssh/$id/"
            }
            if (@(Find-OwnedKey ([IO.File]::ReadAllText($KeyPath+'.pub'))).Count -ne 0) { throw 'HOLD_KEY_STILL_ATTACHED' }
            $detached=$true
            Set-Field $script:Manifest 'key_attach_attempted' $false
            Save-Manifest
        } catch { Write-Host 'Vast public-key detachment is pending; retry Uninstall with network access.' }
        finally { $script:PlainApiKey=$null }
    }
    $config = [string](Get-Field $script:Manifest 'sshd_config' '')
    $block = [string](Get-Field $script:Manifest 'sshd_owned_block' '')
    $authFile = [string](Get-Field $script:Manifest 'authorized_file' '')
    if ($authFile -and (Test-Path -LiteralPath $authFile)) {
        Assert-NoReparse $authFile 'AUTHORIZED_KEY'
        if ((Get-FileHash -LiteralPath $authFile -Algorithm SHA256).Hash.ToLowerInvariant() -ne $script:Manifest.authorized_sha256) { throw 'HOLD_OPERATOR_KEY_FILE_CHANGED' }
        Remove-Item -LiteralPath $authFile -Force
    }
    if ($config -and (Test-Path -LiteralPath $config)) {
        Assert-NoReparse $config 'SSH_CONFIGURATION'
        $text = [IO.File]::ReadAllText($config)
        $matches = [regex]::Matches($text,[regex]::Escape($block))
        if ($block -and $matches.Count -eq 1) {
            $before = $text
            $after = $text.Remove($matches[0].Index,$matches[0].Length)
            $oursUnchanged = (Text-Sha256 $before) -ceq $script:Manifest.sshd_owned_config_sha256
            $backup = Join-Path $LinkRoot 'sshd_config.before'
            if ($oursUnchanged -and -not $script:Manifest.sshd_new -and (Test-Path -LiteralPath $backup)) {
                [IO.File]::WriteAllBytes($config,[IO.File]::ReadAllBytes($backup))
            } else { Write-PlainFile $config $after }
            try { $null = Native-Capture $script:Manifest.sshd_exe @('-t','-f',$config) }
            catch { Write-PlainFile $config $before;throw }
            $service = Get-CimInstance Win32_Service -Filter "Name='sshd'"
            if ($oursUnchanged -and $service.StartMode -eq 'Auto') {
                $start = @{Auto='Automatic';Manual='Manual';Disabled='Disabled'}[[string]$script:Manifest.sshd_prior_start_mode]
                if ($script:Manifest.sshd_prior_state -ne 'Running') { Stop-Service sshd }
                elseif ((Get-Service sshd).Status -eq 'Running') { Restart-Service sshd }
                if ($start) { Set-Service sshd -StartupType $start }
            } elseif ((Get-Service sshd).Status -eq 'Running') { Restart-Service sshd }
        } elseif ($block -and $text.Contains('NOX_PC_LINK_' + $script:Manifest.installation_id)) { throw 'HOLD_OWNED_CONFIG_BLOCK_CHANGED' }
    }
    if ($detached -and $remoteRemoved) {
        foreach ($path in @($KeyPath,($KeyPath+'.pub'),$TokenFile,$KnownHosts)) {
            Assert-NoReparse $path 'OWNED_FILE'
            if (Test-Path -LiteralPath $path -PathType Leaf) { Remove-Item -LiteralPath $path -Force }
        }
        Set-Field $script:Manifest 'phase' 'UNINSTALLED'
        Save-Manifest
        Write-Status 'UNINSTALLED'
        Write-Host 'NOX connection removed. Backups, warm weights, other SSH keys and Windows OpenSSH installation were preserved.'
    } else {
        Set-Field $script:Manifest 'phase' 'UNINSTALL_REMOTE_CLEANUP_PENDING'
        Save-Manifest
        Write-Status 'UNINSTALL_REMOTE_CLEANUP_PENDING'
        Write-Host 'Local connection disabled. Private local credentials are retained only so Uninstall can finish remote cleanup on retry.'
    }
}

try {
    if ($env:OS -ne 'Windows_NT') { throw 'Run this script on your Windows PC.' }
    if ($Mode -in @('Install','Uninstall')) { Assert-Administrator }
    Assert-NoReparse $DestinationRoot 'DESTINATION_ROOT'
    Assert-NoReparse $LinkRoot 'LINK_DIRECTORY'
    $openSshFolder = Join-Path $env:SystemRoot 'System32\OpenSSH'
    if (($env:PATH -split ';') -notcontains $openSshFolder) { $env:PATH = $openSshFolder + ';' + $env:PATH }
    if ($Mode -eq 'Install') {
        if (Test-Path -LiteralPath $ManifestFile) {
            $Manifest = Read-Manifest
            if ($Manifest.phase -eq 'INSTALLED') {
                Write-Host 'This installation already exists. Use Status to check it, or Uninstall before replacing it.'
                Start-ScheduledTask -TaskName $Manifest.task_name
                exit 0
            }
            if ($Manifest.phase -eq 'UNINSTALLED') {
                Move-Item -LiteralPath $ManifestFile -Destination (Join-Path $LinkRoot ('installation.'+$Manifest.installation_id+'.uninstalled.json'))
                $backup = Join-Path $LinkRoot 'sshd_config.before'
                if (Test-Path -LiteralPath $backup) { Move-Item -LiteralPath $backup -Destination ($backup+'.'+$Manifest.installation_id) }
            } else { throw 'HOLD_PARTIAL_INSTALLATION_USE_UNINSTALL' }
        } elseif ((Test-Path -LiteralPath $LinkRoot) -and @(Get-ChildItem -LiteralPath $LinkRoot -Force).Count -ne 0) {
            throw 'HOLD_UNOWNED_LINK_DIRECTORY'
        }
        Protect-Path $LinkRoot -Directory
        $capability = Get-WindowsCapability -Online -Name 'OpenSSH.Client~~~~0.0.1.0'
        if ($capability.State -ne 'Installed') { $null = Add-WindowsCapability -Online -Name 'OpenSSH.Client~~~~0.0.1.0' }
        foreach ($tool in @('ssh.exe','ssh-keygen.exe','ssh-keyscan.exe')) {
            if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw 'HOLD_OPENSSH_CLIENT' }
        }
        $Manifest = [pscustomobject][ordered]@{
            schema='NOX_PC_INSTALL_V1';installation_id=[Guid]::NewGuid().ToString('N');instance_id=$InstanceId;
            owner_sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value;destination_root=$DestinationRoot;
            phase='PREPARING';created_utc=[DateTime]::UtcNow.ToString('o');installed_server_capability=$false;
            connection_may_exist=$false;key_attach_attempted=$false;
            reserve_bytes=([long]$ReserveGiB*1GB);reserve_percent=$ReservePercent
        }
        Save-Manifest
        foreach ($name in @('BACKUPS','WARM')) {
            $path = Join-Path $DestinationRoot $name
            Assert-NoReparse $path 'BACKUP_DIRECTORY'
            $null = New-Item -ItemType Directory -Force -Path $path
        }
        if ((Test-Path -LiteralPath $KeyPath) -or (Test-Path -LiteralPath ($KeyPath+'.pub'))) { throw 'HOLD_UNOWNED_LOCAL_KEY' }
        $comment = 'NOX-PC-LINK-' + $Manifest.installation_id
        $null = Native-Capture 'ssh-keygen.exe' @('-q','-t','ed25519','-N','','-C',$comment,'-f',$KeyPath)
        Protect-Path $KeyPath
        Set-Field $Manifest 'pc_key_fingerprint' (Public-Fingerprint ([IO.File]::ReadAllText($KeyPath+'.pub')))
        Save-Manifest
        Write-Host 'Enter your Vast owner API key locally. Only CurrentUser DPAPI ciphertext is saved for automatic reconnection.'
        $secret = Read-Host 'Vast API key' -AsSecureString
        try { Write-PlainFile $TokenFile (ConvertFrom-SecureString $secret) }
        finally { $secret.Dispose() }
        Set-Field $Manifest 'key_attach_attempted' $true
        Save-Manifest
        Refresh-Route -Attach
        $public = Native-Capture 'ssh.exe' ($SshArguments + @($Target,'cat /root/nox/state/pc_shell/operator_ed25519.pub'))
        if ((Text-Sha256 $public) -cne $OperatorPublicSha256) { throw 'HOLD_SERVER_OPERATOR_KEY_CHANGED' }
        $operator = Public-Identity $public.Trim()
        Install-LocalSsh $operator
        $null = Invoke-Remote 'preflight'
        Register-LinkTask
        Write-Host 'Installed. The logon task is connecting and will retry automatically. Run -Mode Status to verify the first connection.'
        Write-Host 'Backups use BACKUPS and warm weights use WARM under the selected folder. File transfer is a separate verified operation.'
    } elseif ($Mode -eq 'Connect') {
        Run-Connection
    } elseif ($Mode -eq 'Uninstall') {
        Remove-Link
    } else {
        $Manifest = Read-Manifest
        if (Test-Path -LiteralPath $StatusFile) {
            $status = [IO.File]::ReadAllText($StatusFile) | ConvertFrom-Json
            $fresh = ([DateTime]::UtcNow - [DateTime]::Parse($status.checked_utc).ToUniversalTime()).TotalSeconds -le 150
            [pscustomobject]@{State=$status.state;Connected=([bool]$status.connected -and $fresh);Fresh=$fresh;CheckedUtc=$status.checked_utc;Instance=$InstanceId} | Format-List
        } else { Write-Host 'Installed state exists; no verified connection status has been written yet.' }
    }
} catch {
    $message = [string]$_.Exception.Message
    if ($Mode -eq 'Connect') {
        try { Write-Event 'RUNNER_STOPPED';Write-Status 'RUNNER_STOPPED' } catch { }
        exit 2
    }
    if ($message -match '^HOLD_[A-Z0-9_]+$' -or $message.StartsWith('Open Windows PowerShell') -or $message.StartsWith('Run this script')) {
        Write-Error $message
    } else { Write-Error 'NOX PC setup stopped. Existing credentials were not printed. Use -Mode Uninstall to clean up this installation before retrying.' }
    exit 2
} finally { $PlainApiKey=$null }
