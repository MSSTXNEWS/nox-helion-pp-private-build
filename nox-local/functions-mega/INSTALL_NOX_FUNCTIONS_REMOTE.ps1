# ASCII-only Windows PowerShell 5.1 launcher, no encoding ambiguity.
& {
$ErrorActionPreference='Stop'
$root='C:\NOX_HELION\APP\NOX_WEB'
$dest=Join-Path $root 'FUNCTIONS_MEGA_01'
$src=@('WOW_MEGA_01','WOW_V7_FIXED','WOW_V7','WOW_V6','WOW_V5') | ForEach-Object {Join-Path $root $_} | Where-Object {(Test-Path (Join-Path $_ 'server.py')) -and (Test-Path (Join-Path $_ 'chat.html'))} | Select-Object -First 1
if(!$src){throw 'Existing NOX WEB source not found; no files changed'}
if(Test-Path -LiteralPath $dest){throw 'FUNCTIONS_MEGA_01 already exists; previous version preserved'}
Copy-Item -LiteralPath $src -Destination $dest -Recurse -ErrorAction Stop
$patch=Split-Path -Parent $MyInvocation.MyCommand.Path
$names=@('server_mega.py','nox_services.py','nox_push.py','mega-ui.js','mega.css','sw.js','chat-patched.js','setup_vapid.py','nox_connections.example.json')
foreach($n in $names){$file=Join-Path $patch $n;if(!(Test-Path $file)){throw "Missing signed patch: $n"}; Copy-Item -LiteralPath $file -Destination (Join-Path $dest $n) -ErrorAction Stop}
Copy-Item -LiteralPath (Join-Path $patch 'assets\pc_metrics.py') -Destination (Join-Path $dest 'pc_metrics.py') -ErrorAction Stop
$existing=Join-Path $dest 'chat.js'
if(Test-Path $existing){Copy-Item -LiteralPath $existing -Destination (Join-Path $dest 'chat-original.bak.js')}
Copy-Item -LiteralPath (Join-Path $patch 'chat-patched.js') -Destination $existing -Force
# Link the live real library, from existing NOX cache first.
$e=Join-Path $dest 'vendor\fx\echarts.min.js'
if(!(Test-Path $e)){
  $found=Get-ChildItem -LiteralPath $root -Recurse -File -Filter 'echarts.min.js' -ErrorAction SilentlyContinue | Select-Object -First 1
  if($found){New-Item -ItemType Directory -Force -Path (Split-Path -Parent $e) | Out-Null;Copy-Item -LiteralPath $found.FullName -Destination $e}
}
if(!(Test-Path $e)){
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $e) | Out-Null
  Invoke-WebRequest -UseBasicParsing -Uri 'https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js' -OutFile $e -ErrorAction Stop
  if((Get-Item $e).Length -lt 300000){throw 'Incomplete ECharts download'}
}
foreach($name in @('index.html','chat.html','training.html')){
 $path=Join-Path $dest $name
 if(!(Test-Path -LiteralPath $path)){continue}
 $html=[IO.File]::ReadAllText($path)
 if(!$html.Contains('mega-ui.js')){
   $extra='<link rel="stylesheet" href="./mega.css"><script src="./vendor/fx/echarts.min.js" defer></script><script src="./mega-ui.js" defer></script>'
   $html=$html.Replace('</body>',$extra+'</body>')
   [IO.File]::WriteAllText($path,$html,[Text.UTF8Encoding]::new($false))
 }
}
# The broken previous floating telemetry widget must not overlay chat.
foreach($name in @('index.html','chat.html','training.html')){
 $path=Join-Path $dest $name;if(!(Test-Path $path)){continue}
 $html=[IO.File]::ReadAllText($path)
 $html=$html.Replace('<script src="./pc-widgets.js" defer></script>','').Replace('<link rel="stylesheet" href="./pc-widgets.css">','')
 $html=$html.Replace('<script src="./cinema-hud.js" defer></script>','').Replace('<link rel="stylesheet" href="./cinema-hud.css">','')
 [IO.File]::WriteAllText($path,$html,[Text.UTF8Encoding]::new($false))
}
$launcher=Join-Path $dest 'START_NOX_FUNCTIONS.ps1'
$script=@'
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $MyInvocation.MyCommand.Path
$py=Get-Command python.exe -ErrorAction SilentlyContinue
if(!$py){$py=Get-Command py.exe -ErrorAction SilentlyContinue}
if(!$py){throw 'Python 3 required for existing local web bridge'}
New-Item -ItemType Directory -Force -Path (Join-Path $root 'LOGS')|Out-Null
$p=Start-Process -FilePath $py.Source -ArgumentList @((Join-Path $root 'server_mega.py')) -WorkingDirectory $root -PassThru -RedirectStandardOutput (Join-Path $root 'LOGS\mega.stdout.log') -RedirectStandardError (Join-Path $root 'LOGS\mega.stderr.log')
for($i=0;$i -lt 30;$i++){
 try{ $r=Invoke-RestMethod -Uri 'http://127.0.0.1:18773/api/mega/health' -TimeoutSec 2;if($r.status -eq 'READY'){Start-Process 'http://127.0.0.1:18773/';return}}catch{}
 if($p.HasExited){break};Start-Sleep -Milliseconds 250
}
throw 'NOX server did not start; check LOGS\mega.stderr.log'
'@
[IO.File]::WriteAllText($launcher,$script,[Text.UTF8Encoding]::new($true))
Write-Host "NOX FUNCTIONS installed at: $dest" -ForegroundColor Green
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $launcher
}