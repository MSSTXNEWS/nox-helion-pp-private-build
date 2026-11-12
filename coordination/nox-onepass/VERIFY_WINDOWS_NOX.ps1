# NOX Windows physical inventory — read-only. Never starts/stops training or other services.
# Run on the OWNER Windows computer from extracted ONEPASS:
#   powershell -NoProfile -File .\VERIFY_WINDOWS_NOX.ps1 -InventoryOnly
# Real hardware acceptance requires ONEPASS Edge QA separately.
[CmdletBinding()]
param([switch]$InventoryOnly)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSCommandPath
$out=Join-Path $root 'NOX_QA_RESULTS'
New-Item -ItemType Directory -Force -Path $out | Out-Null
$report=[ordered]@{schema='NOX_WINDOWS_PHYSICAL_INVENTORY_V1';timeUtc=[DateTime]::UtcNow.ToString('o');
 source='OWNER_WINDOWS_MACHINE_REQUIRED';kind='READ_ONLY_INVENTORY';userVisualAcceptance='HOLD';
 hardwareGpuAcceptance='HOLD_NOT_EVALUATED';oneHost='HOLD';nativeStop='NOT_TESTED';
 weights='NOT_VERIFIED';s03='NOT_VERIFIED';executable='NOT_VERIFIED';
 inventoryOnly=[bool]$InventoryOnly;warnings=@()}
try{
 $os=Get-CimInstance Win32_OperatingSystem
 $cs=Get-CimInstance Win32_ComputerSystem
 $vc=Get-CimInstance Win32_VideoController
 $report.os=[ordered]@{caption=$os.Caption;version=$os.Version;architecture=$os.OSArchitecture}
 $report.ramBytes=[int64]$cs.TotalPhysicalMemory
 $report.gpus=@($vc | ForEach-Object {
   [ordered]@{name=$_.Name;driverVersion=$_.DriverVersion;
     adapterRAMBytes=if($_.AdapterRAM){[int64]$_.AdapterRAM}else{$null}}
 })
}catch{$report.warnings+=('Hardware inventory unavailable: '+$_.Exception.GetType().Name)}
try{
 $nodeVersion=& node --version 2>$null
 $report.nodeVersion=($nodeVersion | Out-String).Trim()
}catch{$report.nodeVersion='NOT_INSTALLED';$report.warnings+='Node.js 22+ needed for ONEPASS'}
$exe=$env:NOX_EXE_PATH
if($exe -and (Test-Path -LiteralPath $exe -PathType Leaf)){
 try{
  $exeFile=Get-Item -LiteralPath $exe
  $signature=Get-AuthenticodeSignature -LiteralPath $exe
  $report.executable=[ordered]@{path=$exeFile.FullName;size=$exeFile.Length;
   sha256=(Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant();
   signatureStatus=[string]$signature.Status;
   signer=if($signature.SignerCertificate){$signature.SignerCertificate.Subject}else{$null}}
 }catch{$report.warnings+=('EXE readback unavailable: '+$_.Exception.GetType().Name)}
}
# A GET probe is safe. Do not redirect or send credentials, passwords or POST requests.
try{
 $uri='http://127.0.0.1:18775/api/nox/status'
 $response=Invoke-WebRequest -Uri $uri -Method Get -TimeoutSec 4 -MaximumRedirection 0 -UseBasicParsing -ErrorAction Stop
 $json=$response.Content|ConvertFrom-Json
 if($response.StatusCode -eq 200 -and
   $json.backend -eq 'EXISTING_NATIVE_ONEHOST' -and $json.native_p02_bound -eq $true){
   $report.oneHost='NATIVE_STATUS_ENDPOINT_REACHABLE_NOT_FULLY_ACCEPTED'
 }else{$report.oneHost='HOLD_NATIVE_IDENTITY_UNVERIFIED'}
}catch{$report.oneHost='HOLD_ONEHOST_NOT_REACHABLE';$report.warnings+='No local OneHost status receipt (not evidence that local Windows is offline)'}
$dest=Join-Path $out 'windows-hardware-inventory.json'
# This report contains hardware metadata only, no local S03/identity content.
$report|ConvertTo-Json -Depth 8 | Set-Content -Path $dest -Encoding UTF8
Write-Host ('NOX_WINDOWS_PHYSICAL_INVENTORY saved: '+$dest)
Write-Host ('OneHost: '+$report.oneHost+'; GPU evidence: '+$report.hardwareGpuAcceptance+'; native STOP: '+$report.nativeStop)
if(-not $InventoryOnly){
 $runner=Join-Path $root 'NOX_ONEPASS.mjs'
 if(-not(Test-Path -LiteralPath $runner)){throw 'NOX_ONEPASS.mjs missing from extracted bundle'}
 if(($report.nodeVersion -notmatch '^v(2[2-9]|[3-9][0-9])\.')){throw 'Node.js >=22 required'}
 $env:NOX_ONCE='1'
 & node $runner
 exit $LASTEXITCODE
}
exit 0
