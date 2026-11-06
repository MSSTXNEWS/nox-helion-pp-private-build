# NOX Cinema HUD: installs ready ECharts gauges with read-only Windows metrics.
# No pre-existing NOX source tree is overwritten.
& {
$ErrorActionPreference='Stop'
[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
$root='C:\NOX_HELION\APP\NOX_WEB'
$dest=Join-Path $root 'WOW_CINEMA_HUD'
$src=$null
foreach($name in @('WOW_MEGA_01','WOW_V7_FIXED','WOW_V7','WOW_V6','WOW_V5')) {
 $test=Join-Path $root $name
 if((Test-Path (Join-Path $test 'server.py')) -and (Test-Path (Join-Path $test 'chat.html')) -and (Test-Path (Join-Path $test 'index.html'))) {$src=$test;break}
}
if(!$src){throw 'NOX installed sources were not found; nothing changed'}
if(Test-Path $dest){throw 'WOW_CINEMA_HUD already exists. Existing files are preserved.'}
Copy-Item -LiteralPath $src -Destination $dest -Recurse -ErrorAction Stop
$base='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/785287af0bb08f77ef981ad0582b6bd9815ac67e/nox-local/cinema-hud'
$files=@('pc_metrics.py','cinema-hud.css','cinema-hud.js')
foreach($name in $files){
 $path=Join-Path $dest $name
 Invoke-WebRequest -UseBasicParsing -Uri "$base/$name" -OutFile $path -ErrorAction Stop
 if((Get-Item $path).Length -lt 1000){throw "Downloaded file invalid: $name"}
}
$lib=Join-Path $dest 'vendor\hud\echarts.min.js'
New-Item -ItemType Directory -Force -Path (Split-Path $lib -Parent) | Out-Null
$already=@(Get-ChildItem -LiteralPath $src -Recurse -Filter 'echarts.min.js' -File -ErrorAction SilentlyContinue | Where-Object {$_.Length -gt 400000} | Select-Object -First 1)
if($already.Count){Copy-Item -LiteralPath $already[0].FullName -Destination $lib -ErrorAction Stop}
else{Invoke-WebRequest -UseBasicParsing 'https://cdn.jsdelivr.net/npm/echarts@5.6.0/dist/echarts.min.js' -OutFile $lib -ErrorAction Stop}
if((Get-Item $lib).Length -lt 400000){throw 'ECharts source incomplete'}
$serverPath=Join-Path $dest 'server.py'
$server=[IO.File]::ReadAllText($serverPath)
if(!$server.Contains('import pc_metrics')){$server=$server.Replace('from pathlib import Path','from pathlib import Path' + "`nimport pc_metrics")}
if(!$server.Contains("'/api/pc-metrics'")){
 $anchor='    def do_GET(self):'
 if(!$server.Contains($anchor) -or !$server.Contains('def _json(')){throw 'Unknown NOX server API contract; not modified'}
 $inject="    def do_GET(self):`n        if self.path.split('?',1)[0]=='/api/pc-metrics':`n            return self._json(200,pc_metrics.read())"
 $server=$server.Replace($anchor,$inject)
}
$server=[regex]::Replace($server,'(?m)^PORT\s*=\s*\d+','PORT=18772',1)
[IO.File]::WriteAllText($serverPath,$server,[Text.UTF8Encoding]::new($false))
foreach($name in @('index.html','chat.html','training.html')){
 $path=Join-Path $dest $name
 if(!(Test-Path $path)){continue}
 $html=[IO.File]::ReadAllText($path)
 if(!$html.Contains('cinema-hud.js')){
  if(!$html.Contains('</body>')){throw "Unexpected HTML: $name"}
  $extra='<link rel="stylesheet" href="./cinema-hud.css"><script src="./vendor/hud/echarts.min.js" defer></script><script src="./cinema-hud.js" defer></script>'
  $html=$html.Replace('</body>',$extra+'</body>')
 }
 if($html.Contains('pc-widgets.js')){$html=$html.Replace('<script src="./pc-widgets.js" defer></script>','')}
 [IO.File]::WriteAllText($path,$html,[Text.UTF8Encoding]::new($false))
}
$css=Join-Path $dest 'nox.css'
if(Test-Path $css){Add-Content -LiteralPath $css -Encoding UTF8 -Value "`n#nox-live-widgets{display:none!important}`n"}
$launcher=Join-Path $dest 'START_NOX_WEB.ps1'
if(!(Test-Path $launcher)){throw 'Missing NOX launcher in copied source'}
$ps=[IO.File]::ReadAllText($launcher)
$ps=[regex]::Replace($ps,'1876\d|18770|18771','18772')
[IO.File]::WriteAllText($launcher,$ps,[Text.UTF8Encoding]::new($false))
$python=Get-Command python.exe -ErrorAction SilentlyContinue
if($python){& $python.Source -m py_compile (Join-Path $dest 'pc_metrics.py') (Join-Path $dest 'server.py');if($LASTEXITCODE -ne 0){throw 'Python syntax test failed'}}
$manifest=[ordered]@{source=$src;new_folder=$dest;echarts='5.6.0';port=18772;metric_source='Windows read only; GPU Engine estimate if supported';cpu_gpu_thermal_warning_c=65;auto_pause_training=$false;weight_changes=$false;sqlite_changes=$false;created=(Get-Date).ToString('o')}
$manifest|ConvertTo-Json|Set-Content (Join-Path $dest 'CINEMA_HUD_MANIFEST.json') -Encoding UTF8
Write-Host 'NOX CINEMA HUD READY: original home and CHAT plus 3 live ECharts gauges' -ForegroundColor Green
Write-Host 'GPU counters may be N/D on unsupported AMD drivers; no fake data.'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $launcher
}