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
    machine = 'WINDOWS_OWNER_HOST'
    package_status = 'HOLD_NOT_VERIFIED'
    package_sha256 = $null
    package_entries = $null
    expected_package_entries = 1091
    powershell_version = $PSVersionTable.PSVersion.ToString()
    nox_start_script_present = $false
    local_web_directory_present = $false
    localhost_web_port_18775 = 'NOT_CHECKED'
    localhost_chat_port_18877 = 'NOT_CHECKED'
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
$report_path = Join-Path $dir ('NOX_ONEPASS_WINDOWS_READONLY_RECEIPT_'+[DateTime]::UtcNow.ToString('yyyyMMdd_HHmmss')+'.json')
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $report_path -Encoding UTF8
Write-Host ('NOX · Пакет: '+$report.package_status)
Write-Host ('NOX · Локальная WEB-служба: '+$report.localhost_web_port_18775)
Write-Host ('NOX · Локальный чат-порт: '+$report.localhost_chat_port_18877)
Write-Host ('NOX · Квитанция: '+$report_path)
Write-Host 'Физическая приёмка модели, S03 и GPU не проводилась. Никаких служб или весов не меняли.'
if ($report.package_status -ne 'SOURCE_HASH_AND_STRUCTURE_PASS') { exit 2 }
exit 0
