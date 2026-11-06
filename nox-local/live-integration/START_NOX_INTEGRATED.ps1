$ErrorActionPreference='Stop'
$root=Split-Path -Parent $MyInvocation.MyCommand.Path
$port=18775
$python=Get-Command python.exe -ErrorAction SilentlyContinue
if(!$python){throw 'Python 3 not found in PATH. NOX source preserved.'}
if(!(Test-Path (Join-Path $root 'server_integrated.py'))){throw 'NOX integrated server missing'}
if(!(Test-Path (Join-Path $root 'vendor\fx\echarts.min.js'))){throw 'ECharts original library missing'}
$existing=Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if($existing){
  try{
    $health=Invoke-RestMethod "http://127.0.0.1:$port/api/nox/pages" -TimeoutSec 2
    if($health.pages.Count -eq 9){Write-Host 'Existing NOX integrated instance verified.' -ForegroundColor Green;Start-Process "http://127.0.0.1:$port/";return}
  }catch{}
  throw "Port $port is occupied by another service. No process killed."
}
$log=Join-Path $root 'LOGS'
New-Item -ItemType Directory -Force -Path $log|Out-Null
$arguments=@('-u',(Join-Path $root 'server_integrated.py'))
$proc=Start-Process -FilePath $python.Source -ArgumentList $arguments -WorkingDirectory $root -RedirectStandardOutput (Join-Path $log 'integrated.stdout.log') -RedirectStandardError (Join-Path $log 'integrated.stderr.log') -PassThru
for($i=0;$i -lt 45;$i++){
  if($proc.HasExited){throw 'NOX integrated server exited; see LOGS/integrated.stderr.log'}
  try{
    $a=Invoke-RestMethod "http://127.0.0.1:$port/api/nox/pages" -TimeoutSec 2
    $b=Invoke-RestMethod "http://127.0.0.1:$port/api/mega/health" -TimeoutSec 2
    if($a.pages.Count -eq 9 -and $b.status -eq 'READY'){
      Write-Host "NOX LIVE: http://127.0.0.1:$port/" -ForegroundColor Green
      Start-Process "http://127.0.0.1:$port/"
      return
    }
  }catch{}
  Start-Sleep -Milliseconds 250
}
throw 'NOX integrated server failed health check; see local LOGS'