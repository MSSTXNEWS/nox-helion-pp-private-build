# NOX HELION WEB 11-22 | existing Python browser server, no EXE, no second backend
[CmdletBinding()]
param(
 [string]$Root='C:\NOX_HELION\APP\NOX_WEB',
 [ValidateRange(1024,65535)][int]$Port=18775,
 [switch]$NoBrowser,
 [switch]$ProbeOnly
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
$target=Join-Path $Root 'NOX_LIVE'
$server=Join-Path $target 'server_live.py'
$receipt=Join-Path $target 'NOX_WEB_11_22_RECEIPT.json'
$url="http://127.0.0.1:$Port"
if($Port -ne 18775){throw 'NOX_LIVE_PINNED_PORT_HOLD: do not use a competing instance'}
if(!(Test-Path -LiteralPath $server -PathType Leaf)){throw "ORIGINAL_NOX_LIVE_SERVER_MISSING_HOLD: $server"}
if(!(Test-Path -LiteralPath $receipt -PathType Leaf)){throw "NOX_WEB_SOURCE_RECEIPT_MISSING_HOLD: $receipt"}
$installation=Get-Content -LiteralPath $receipt -Raw -Encoding UTF8|ConvertFrom-Json
if($installation.schema -ne 'NOX_WEB_11_22_INSTALLED_SOURCE_V1'){
 throw 'NOX_WEB_RECEIPT_SCHEMA_HOLD: not a verified original-source overlay'
}
function Get-Health{
 try{
  $r=Invoke-RestMethod "$url/api/mega/health" -TimeoutSec 3 -ErrorAction Stop
  if($r.status -eq 'READY' -and $r.identity -eq 'NOX_LOCAL_LIVE_V1' -and
    $r.releaseAccepted -eq $false -and $r.scope -eq 'read-only adapters'){return $true}
 }catch{}
 return $false
}
function Get-Owner {
 $conn=@(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
 if($conn.Count -eq 0){return 0}
 $ids=@($conn|Select-Object -ExpandProperty OwningProcess -Unique)
 if($ids.Count -ne 1){throw 'NOX_WEB_PORT_MULTIPLE_OWNERS_HOLD'}
 $proc=Get-CimInstance Win32_Process -Filter ("ProcessId = "+[int]$ids[0])
 if(!$proc -or ![string]$proc.CommandLine){throw 'NOX_WEB_PORT_OWNER_UNREADABLE_HOLD'}
 if([string]$proc.Name -notmatch '(?i)^python(w)?\.exe$' -or
    [string]$proc.CommandLine -notmatch [regex]::Escape('server_live.py') -or
    [string]$proc.CommandLine -notmatch [regex]::Escape('NOX_LIVE')){
  throw "FOREIGN_PROCESS_ON_WEB_PORT_HOLD: PID $($ids[0]); nothing stopped"
 }
 return [int]$ids[0]
}
$owner=Get-Owner
if($owner -ne 0){
 if(-not (Get-Health)){throw "NOX_WEB_PORT_OWNER_HEALTH_MISMATCH_HOLD: PID $owner"}
 Write-Host "NOX WEB verified: $url / existing PID $owner" -ForegroundColor Green
} else {
 if($ProbeOnly){throw 'NOX_WEB_NOT_RUNNING_HOLD'}
 $py=Get-Command python.exe -ErrorAction SilentlyContinue
 if(!$py){throw 'EXISTING_PYTHON_NOT_FOUND_HOLD: no automatic runtime download'}
 $logdir=Join-Path $target 'LOGS'
 New-Item -ItemType Directory -Force -Path $logdir|Out-Null
 $stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
 $proc=Start-Process -FilePath $py.Source -ArgumentList @($server) -WorkingDirectory $target -RedirectStandardOutput (Join-Path $logdir "web_$stamp.stdout.log") -RedirectStandardError (Join-Path $logdir "web_$stamp.stderr.log") -PassThru
 $ok=$false
 for($attempt=0;$attempt -lt 40;$attempt++){
  if($proc.HasExited){break}
  if(Get-Health){$ok=$true;break}
  Start-Sleep -Milliseconds 400
 }
 if(-not $ok){throw "NOX_WEB_BOOT_NOT_VERIFIED_HOLD: PID $($proc.Id); inspect $logdir"}
 if((Get-Owner) -eq 0){throw 'NOX_WEB_LISTENER_MISSING_AFTER_START_HOLD'}
 Write-Host "NOX WEB running from original source: $url / PID $($proc.Id)" -ForegroundColor Green
}
foreach($endpoint in @('/api/status','/api/s03/status','/api/training/status','/api/pc-metrics')){
 try{
  $response=Invoke-RestMethod "$url$endpoint" -TimeoutSec 5
  if($null -eq $response){throw 'empty response'}
  Write-Host "$endpoint | API RESPONDED (not functionality proof)"
 }catch{Write-Warning "$endpoint | HOLD $($_.Exception.GetType().Name)"}
}
try{
 $tags=Invoke-RestMethod "$url/api/status" -TimeoutSec 5
 if($tags.ollama_online -eq $true -and @($tags.models).Count -gt 0){
  Write-Host "Ollama connected | $(@($tags.models).Count) installed model(s)" -ForegroundColor Cyan
 } else {Write-Warning 'OLLAMA_MODEL_OFFLINE_HOLD: WEB can open but chat inference not proven'}
}catch{Write-Warning 'OLLAMA_STATUS_UNKNOWN_HOLD'}
if(-not $NoBrowser){Start-Process "$url/"}
