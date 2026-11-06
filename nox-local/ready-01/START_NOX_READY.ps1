$ErrorActionPreference='Stop'
$root=Split-Path -Parent $MyInvocation.MyCommand.Path
if(!(Test-Path (Join-Path $root 'vendor\blackhole\sceneblackhole.html'))){throw 'Original Black Hole scene missing. Run INSTALL_NOX_READY.ps1 first.'}
if(!(Test-Path (Join-Path $root 'vendor\fx\echarts.min.js'))){throw 'Original ECharts library missing. Run INSTALL_NOX_READY.ps1 first.'}
$python=Get-Command python.exe -ErrorAction SilentlyContinue
if(!$python){throw 'Python 3 is needed for existing local NOX bridge'}
$logs=Join-Path $root 'LOGS';New-Item -ItemType Directory -Force $logs|Out-Null
$proc=Start-Process -FilePath $python.Source -ArgumentList @((Join-Path $root 'server_mega.py')) -WorkingDirectory $root -RedirectStandardOutput (Join-Path $logs 'stdout.log') -RedirectStandardError (Join-Path $logs 'stderr.log') -PassThru
for($i=0;$i -lt 36;$i++){
  if($proc.HasExited){throw 'Server startup failed; see LOGS\stderr.log'}
  try{$r=Invoke-RestMethod 'http://127.0.0.1:18774/api/mega/health' -TimeoutSec 2;if($r.status -eq 'READY'){Start-Process 'http://127.0.0.1:18774/';Write-Host 'NOX READY: http://127.0.0.1:18774/' -ForegroundColor Green;return}}catch{}
  Start-Sleep -Milliseconds 250
}
throw 'Server did not pass local health check'