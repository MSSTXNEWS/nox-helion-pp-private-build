# NOX ONEPASS: safe Windows acceptance preflight, without installing or restarting.
# Read-only artifact/port/file checks. Only writes one JSON receipt in this folder.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$expectedHash = '45893adaf1fa49991dbb9f61f3d5cc4f2273eddf5d6f2e2548cf57d0b09fb947'
$file = Join-Path $dir 'NOX_HELION_WEB_V293_ONEPASS_NATIVE_COMPAT.zip'
$report = [ordered]@{
    schema = 'NOX_ONEPASS_WINDOWS_READONLY_PROBE_V1'
    at_utc = [DateTime]::UtcNow.ToString('o')
    machine = 'LOCAL_EXECUTION_HOST_NOT_OWNER_ATTESTED'
    windows_owner_pc_identity_attested = $false
    package_status = 'HOLD_NOT_VERIFIED'
    package_sha256 = $null
    package_entries = $null
    expected_package_entries = 1091
    powershell_version = $PSVersionTable.PSVersion.ToString()
    nox_start_script_present = $false
    local_web_directory_present = $false
    localhost_web_port_18775 = 'NOT_CHECKED'
    localhost_chat_port_18877 = 'NOT_CHECKED'
    windows_owner_pc_port_8766 = 'NOT_CHECKED'
    windows_pc_status_anonymous = 'NOT_TESTED'
    windows_pc_capabilities_anonymous = 'NOT_TESTED'
    windows_pc_owner_cookie_e2e = 'NOT_TESTED'
    windows_pc_backup_handler_authenticated = $false
    windows_pc_handler_registration_verified = $false
    owner_authenticated_model_response = 'NOT_TESTED'
    s03_write_readback = 'NOT_TESTED'
    GPU_STOP_physical = 'NOT_TESTED'
    full_weight_learning_checkpoint = 'NOT_TESTED'
    owner_windows_browser_visual = 'NOT_TESTED'
    original_S03_weights_modified = $false
    software_installed_or_services_restarted = $false
    release_92_functions_accepted = $false
    errors = @()
}
function Test-LocalPort([int]$port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $handle = $client.BeginConnect('127.0.0.1', $port, $null, $null)
        if (-not $handle.AsyncWaitHandle.WaitOne(1200)) { return 'UNREACHABLE' }
        $client.EndConnect($handle)
        return 'TCP_REACHABLE_NOT_FUNCTIONAL_E2E'
    } catch { return 'UNREACHABLE' }
    finally { $client.Close() }
}
# NOX_V147_RECEIPT_NO_CLOBBER_BEGIN
# Atomic exclusive creation: repeated same-second receipts must never be overwritten.
function Write-NoClobberOnepassReceipt([string]$receiptPath, [string]$json) {
    $bytes = ([System.Text.UTF8Encoding]::new($false)).GetBytes($json)
    $stream = [System.IO.FileStream]::new(
        $receiptPath,
        [System.IO.FileMode]::CreateNew,
        [System.IO.FileAccess]::Write,
        [System.IO.FileShare]::None
    )
    try {
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Flush($true)
    } finally {
        $stream.Dispose()
    }
}
# NOX_V147_RECEIPT_NO_CLOBBER_END
# NOX_V146_WINDOWS_PC_PROBE_BEGIN
# Anonymous, read-only Windows PC route discovery: NOT authenticated E2E.
# Strictly GET two allowlisted localhost routes, never POST /api/install/backup.
function Test-AnonymousPcRoute([string]$path) {
    if (@('/api/nox/status','/api/install/capabilities') -notcontains $path) {
        throw 'HOLD_WINDOWS_PC_UNAPPROVED_READONLY_ROUTE'
    }
    try {
        $request = [System.Net.HttpWebRequest][System.Net.WebRequest]::Create('http://127.0.0.1:8766' + $path)
        $request.Method = 'GET'
        $request.AllowAutoRedirect = $false
        $request.UseDefaultCredentials = $false
        $request.Credentials = $null
        $request.PreAuthenticate = $false
        $request.CookieContainer = New-Object System.Net.CookieContainer
        $request.Proxy = $null
        $request.KeepAlive = $false
        $request.Timeout = 2000
        $request.ReadWriteTimeout = 2000
        $response = $null
        try {
            $response = [System.Net.HttpWebResponse]$request.GetResponse()
            $code = [int]$response.StatusCode
        } catch [System.Net.WebException] {
            $response = $_.Exception.Response
            if (-not ($response -is [System.Net.HttpWebResponse])) {
                return 'UNREACHABLE_OR_PROBE_FAILED'
            }
            $code = [int]$response.StatusCode
        } finally {
            if ($null -ne $response) { $response.Close() }
        }
        # An anonymous 404 can mask an existing owner-only route via ACL;
        # neither 200 nor 404 attests handler registration or owner-cookie.
        switch ($code) {
            200 { return 'ANONYMOUS_200_NO_OWNER_PROOF' }
            401 { return 'AUTH_REQUIRED_NO_OWNER_PROOF' }
            403 { return 'AUTH_REQUIRED_NO_OWNER_PROOF' }
            404 { return 'HTTP_404_AUTH_MASKED_OR_ROUTE_UNKNOWN' }
            405 { return 'GET_NOT_ALLOWED_UNVERIFIED' }
            301 { return 'REDIRECT_REJECTED' }
            302 { return 'REDIRECT_REJECTED' }
            307 { return 'REDIRECT_REJECTED' }
            308 { return 'REDIRECT_REJECTED' }
            default { return ('HTTP_'+$code+'_UNVERIFIED') }
        }
    } catch {
        return 'UNREACHABLE_OR_PROBE_FAILED'
    }
}
# NOX_V146_WINDOWS_PC_PROBE_END
try {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw 'HOLD_DERIVED_ZIP_NOT_FOUND' }
    $sha = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
    $report.package_sha256 = $sha
    if ($sha -ne $expectedHash) { throw 'HOLD_DERIVED_ZIP_HASH_MISMATCH' }
    Add-Type -AssemblyName System.IO.Compression -ErrorAction Stop
    Add-Type -AssemblyName System.IO.Compression.FileSystem -ErrorAction Stop
    $zip = [System.IO.Compression.ZipFile]::OpenRead($file)
    try {
        $report.package_entries = $zip.Entries.Count
        if ($report.package_entries -ne 1091) { throw 'HOLD_WRONG_ZIP_ENTRY_COUNT' }
        $names = @($zip.Entries | ForEach-Object { $_.FullName })
        if (-not ($names -contains 'site/nox-legacy-chat-bridge-v293.js')) { throw 'HOLD_MISSING_COMPAT_MODULE' }
        if (-not ($names -contains 'site/nox-chat.js')) { throw 'HOLD_MISSING_ORIGINAL_CHAT' }
    } finally { $zip.Dispose() }
    $report.package_status = 'SOURCE_HASH_AND_STRUCTURE_PASS'
} catch {
    $report.errors = @($report.errors) + [string]$_.Exception.Message
}
$report.nox_start_script_present = Test-Path -LiteralPath 'C:\NOX_HELION\NOX_NEW\NOX_START.ps1' -PathType Leaf
$report.local_web_directory_present = Test-Path -LiteralPath 'C:\NOX_HELION\APP\NOX_WEB\NOX_LIVE' -PathType Container
$report.localhost_web_port_18775 = Test-LocalPort 18775
$report.localhost_chat_port_18877 = Test-LocalPort 18877
# Check only anonymous GETs to original Windows localhost. Never execute backup.
$report.windows_owner_pc_port_8766 = Test-LocalPort 8766
$report.windows_pc_status_anonymous = Test-AnonymousPcRoute '/api/nox/status'
$report.windows_pc_capabilities_anonymous = Test-AnonymousPcRoute '/api/install/capabilities'
$report_path = Join-Path $dir ('NOX_ONEPASS_WINDOWS_READONLY_RECEIPT_'+[DateTime]::UtcNow.ToString('yyyyMMdd_HHmmss')+'.json')
try {
    Write-NoClobberOnepassReceipt $report_path ($report | ConvertTo-Json -Depth 8)
} catch {
    Write-Host ('HOLD_RECEIPT_NO_REPLACE_FAILED: '+$_.Exception.GetType().Name)
    exit 3
}
Write-Host ('NOX · Пакет: '+$report.package_status)
Write-Host ('NOX · Локальная WEB-служба: '+$report.localhost_web_port_18775)
Write-Host ('NOX · Локальный чат-порт: '+$report.localhost_chat_port_18877)
Write-Host ('NOX · Windows PC :8766 (anonymous only): '+$report.windows_owner_pc_port_8766)
Write-Host ('NOX · PC status/capabilities (not owner-cookie proof): '+$report.windows_pc_status_anonymous+' / '+$report.windows_pc_capabilities_anonymous)
Write-Host ('NOX · Квитанция: '+$report_path)
Write-Host 'Физическая приёмка модели, S03 и GPU не проводилась. Никаких служб или весов не меняли.'
if ($report.package_status -ne 'SOURCE_HASH_AND_STRUCTURE_PASS') { exit 2 }
exit 0
