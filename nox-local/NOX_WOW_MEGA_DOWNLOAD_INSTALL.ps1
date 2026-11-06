# NOX LOCAL · WOW MEGA PACK 01 · Local ready engines + telemetry + notifications.
# Existing NOX/SQLite/Ollama/models never changed. Original upstream sources retained.
& {
$ErrorActionPreference='Stop'
[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
$root='C:\NOX_HELION\APP\NOX_WEB'
$dest=Join-Path $root 'WOW_MEGA_01'
$sourceCandidates=@('WOW_V7_FIXED','WOW_V7','WOW_V6','WOW_V5')
$src=$null
foreach($n in $sourceCandidates){$p=Join-Path $root $n;if((Test-Path (Join-Path $p 'server.py')) -and (Test-Path (Join-Path $p 'index.html')) -and (Test-Path (Join-Path $p 'chat.html'))){$src=$p;break}}
if(!$src){throw 'NOX original V5/V6/V7 not found under C:\NOX_HELION\APP\NOX_WEB; nothing changed.'}
Write-Host "NOX existing source: $src" -ForegroundColor Cyan
if(!(Test-Path $dest)){Copy-Item -LiteralPath $src -Destination $dest -Recurse -ErrorAction Stop}
$vendor=Join-Path $dest 'vendor'
$gallery=Join-Path $dest 'wow-gallery'
New-Item -ItemType Directory -Force -Path $gallery,(Join-Path $gallery 'blackhole'),(Join-Path $gallery 'three'),(Join-Path $vendor 'fx') | Out-Null
$downloaded=New-Object System.Collections.ArrayList
$reused=New-Object System.Collections.ArrayList
$failed=New-Object System.Collections.ArrayList
function Fetch-Asset([string]$url,[string]$path,[int]$min=100) {
  $rel=$path.Substring($dest.Length).TrimStart('\')
  if((Test-Path -LiteralPath $path) -and (Get-Item -LiteralPath $path).Length -ge $min){[void]$reused.Add($rel);return $true}
  $dir=Split-Path -Parent $path;New-Item -ItemType Directory -Force -Path $dir | Out-Null
  $partial="$path.part"
  try{
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $partial -TimeoutSec 120 -ErrorAction Stop
    if((Get-Item -LiteralPath $partial).Length -lt $min){throw 'Truncated content'}
    Move-Item -LiteralPath $partial -Destination $path -Force
    [void]$downloaded.Add($rel)
    return $true
  }catch{
    [void]$failed.Add([pscustomobject]@{file=$rel;reason=$_.Exception.Message;source=$url})
    Write-Warning "Source download failed: $rel"
    return $false
  }finally{if(Test-Path -LiteralPath $partial){Remove-Item -LiteralPath $partial -Force}}
}
$bh='https://raw.githubusercontent.com/sysscan/3d-blackhole-simulation/9cd793f34b972f6c8928b0d3127d94eff7613a61'
Fetch-Asset "$bh/index.html" (Join-Path $gallery 'blackhole/SOURCE.html') 20000 | Out-Null
Fetch-Asset "$bh/LICENSE" (Join-Path $gallery 'blackhole/LICENSE') 900 | Out-Null
$three128=Join-Path $gallery 'blackhole/three.min.js'
Fetch-Asset 'https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js' $three128 400000 | Out-Null
$orig=Join-Path $gallery 'blackhole/SOURCE.html'
$index=Join-Path $gallery 'blackhole/index.html'
if((Test-Path $orig) -and (Test-Path $three128)){
   $x=[IO.File]::ReadAllText($orig)
   $needle='https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js'
   if($x.Contains($needle)){
      $x=$x.Replace($needle,'./three.min.js')
      if(!(Test-Path $index)){[IO.File]::WriteAllText($index,$x,[Text.UTF8Encoding]::new($false))}
   }else{[void]$failed.Add([pscustomobject]@{file='blackhole/index.html';reason='Unexpected upstream source';source=$bh})}
}
# Ready examples: original Three.js source (official tags/commit, no hand-painted substitute).
$threeRepo='https://raw.githubusercontent.com/mrdoob/three.js/49ab5be70757f55c2ae9e9b19c10a8b4b850229b/examples'
foreach($name in @('webgl_shader_lava.html','webgl_shader.html','webgl_postprocessing_unreal_bloom.html','webgl_materials_physical_clearcoat.html','webgl_postprocessing_godrays.html')){
    Fetch-Asset "$threeRepo/$name" (Join-Path $gallery "three/$name") 1200 | Out-Null
}
# Curated distributions for shader motion, UI, telemetry. Full development repositories intentionally not duplicated.
$fx=@(
 @('gsap.min.js','https://cdn.jsdelivr.net/npm/gsap@3.12.5/dist/gsap.min.js',10000),
 @('particles.min.js','https://cdn.jsdelivr.net/npm/particles.js@2.0.0/particles.min.js',10000),
 @('lottie.min.js','https://cdn.jsdelivr.net/npm/lottie-web@5.12.2/build/player/lottie.min.js',10000),
 @('echarts.min.js','https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js',100000),
 @('uPlot.iife.min.js','https://cdn.jsdelivr.net/npm/uplot@1.6.32/dist/uPlot.iife.min.js',10000),
 @('uPlot.min.css','https://cdn.jsdelivr.net/npm/uplot@1.6.32/dist/uPlot.min.css',1000),
 @('lucide.min.js','https://cdn.jsdelivr.net/npm/lucide@0.468.0/dist/umd/lucide.min.js',10000)
)
foreach($row in $fx){Fetch-Asset ([string]$row[1]) (Join-Path $vendor ('fx/'+$row[0])) ([int]$row[2]) | Out-Null}
# Reuse ready authored UI already delivered, not a new HTML imitation.
$tabler=Join-Path $vendor 'tabler/tabler.min.css'
if(Test-Path $tabler){[void]$reused.Add('vendor/tabler/tabler.min.css')}
# Real read-only Windows telemetry API. Existing backend is copied; user data untouched.
$metricsPy=Join-Path $dest 'pc_metrics.py'
[IO.File]::WriteAllText($metricsPy, @'
"""Read-only, local-only PC telemetry for NOX. No synthetic values."""
import ctypes, subprocess, shutil, os, time
from ctypes import wintypes

class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [('dwLength', wintypes.DWORD),('dwMemoryLoad', wintypes.DWORD),
        ('ullTotalPhys',ctypes.c_ulonglong),('ullAvailPhys',ctypes.c_ulonglong),
        ('ullTotalPageFile',ctypes.c_ulonglong),('ullAvailPageFile',ctypes.c_ulonglong),
        ('ullTotalVirtual',ctypes.c_ulonglong),('ullAvailVirtual',ctypes.c_ulonglong),
        ('ullAvailExtendedVirtual',ctypes.c_ulonglong)]

_cache=(0,{})
def read():
    global _cache
    now=time.monotonic()
    if now-_cache[0]<5: return _cache[1]
    out={'source':'windows-local','sample_age_seconds':0,'cpu_percent':None,'ram_used_gb':None,
         'ram_total_gb':None,'ram_percent':None,'gpu_percent':None,'vram_used_gb':None,
         'vram_total_gb':None,'gpu_temperature_c':None,'gpu_power_w':None,'errors':[]}
    try:
        m=MEMORYSTATUSEX();m.dwLength=ctypes.sizeof(m)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
            out['ram_total_gb']=round(m.ullTotalPhys/(1024**3),2)
            out['ram_used_gb']=round((m.ullTotalPhys-m.ullAvailPhys)/(1024**3),2)
            out['ram_percent']=m.dwMemoryLoad
    except Exception as e: out['errors'].append('RAM unavailable')
    try:
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)
        cmd=['powershell.exe','-NoProfile','-NonInteractive','-Command',
             '(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average']
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
             text=True,timeout=5,creationflags=creationflags)
        if p.returncode==0 and p.stdout.strip():
            out['cpu_percent']=round(float(p.stdout.strip().replace(',','.')),1)
    except Exception: out['errors'].append('CPU unavailable')
    nvsmi=shutil.which('nvidia-smi')
    if not nvsmi:
        nvsmi=r'C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe'
        if not os.path.isfile(nvsmi): nvsmi=None
    if nvsmi:
        try:
            p=subprocess.run([nvsmi,'--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw',
                              '--format=csv,noheader,nounits'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                              text=True,timeout=4,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if p.returncode==0:
                raw=[x.strip() for x in p.stdout.strip().splitlines()[0].split(',')]
                vals=[float(x.replace(',','.')) if x.lower() not in ('[not supported]','n/a','') else None for x in raw[:5]]
                for k,v in zip(['gpu_percent','vram_used_gb','vram_total_gb','gpu_temperature_c','gpu_power_w'],vals):
                    if k.startswith('vram_') and v is not None:v=round(v/1024,2)
                    out[k]=v
        except Exception: out['errors'].append('NVIDIA telemetry unavailable')
    else: out['errors'].append('NVIDIA telemetry unavailable')
    _cache=(now,out)
    return out

'@, [Text.UTF8Encoding]::new($false))
$widgetsJs=Join-Path $dest 'pc-widgets.js'
$widgetsCss=Join-Path $dest 'pc-widgets.css'
[IO.File]::WriteAllText($widgetsJs,@'
/* NOX telemetry + notifications, local-only and optional browser permission. */
(()=>{'use strict';
let root=document.getElementById('nox-live-widgets');if(root)return;
root=document.createElement('aside');root.id='nox-live-widgets';
root.innerHTML=`<div class="nox-monitor-head"><b>СОСТОЯНИЕ ПК</b><button id="nox-notify-toggle" aria-label="Уведомления" title="Уведомления">♧ <span id="nox-alert-count">0</span></button></div><div class="nox-monitor-values"><span>CPU <b data-k="cpu_percent">Н/Д</b></span><span>RAM <b data-k="ram_percent">Н/Д</b></span><span>GPU <b data-k="gpu_percent">Н/Д</b></span><span>VRAM <b data-k="vram_used_gb">Н/Д</b></span><span>°C <b data-k="gpu_temperature_c">Н/Д</b></span></div><div id="nox-notice" role="status" aria-live="polite">Проверка датчиков…</div><div id="nox-alert-list" hidden></div>`;
document.body.appendChild(root);
const status=root.querySelector('#nox-notice'),list=root.querySelector('#nox-alert-list');let lastOnline=null,count=0;
function notice(t){status.textContent=t;const e=document.createElement('div');e.textContent=new Date().toLocaleTimeString('ru-RU')+' · '+t;list.prepend(e);while(list.children.length>12)list.lastElementChild.remove();count++;root.querySelector('#nox-alert-count').textContent=count;if('Notification' in window&&Notification.permission==='granted'&&document.hidden){try{new Notification('NOX HELION',{body:t,tag:'nox-local-event'})}catch{}}}
root.querySelector('#nox-notify-toggle').addEventListener('click',async()=>{list.hidden=!list.hidden;if('Notification'in window&&Notification.permission==='default'){try{let s=await Notification.requestPermission();notice(s==='granted'?'Системные уведомления разрешены':'Уведомления доступны внутри NOX')}catch{notice('Уведомления только внутри NOX')}}});
async function update(){try{let [mr,sr]=await Promise.all([fetch('/api/pc-metrics',{cache:'no-store'}),fetch('/api/status',{cache:'no-store'})]);if(!mr.ok)throw Error('local metrics unavailable');let x=await mr.json();for(const k of ['cpu_percent','ram_percent','gpu_percent','vram_used_gb','gpu_temperature_c']){let e=root.querySelector(`[data-k="${k}"]`);let v=x[k];e.textContent=v==null?'Н/Д':`${v}${k.endsWith('percent')?'%':k==='vram_used_gb'?' ГБ':k==='gpu_temperature_c'?'°':''}`;}status.textContent='Локальная телеметрия · '+new Date().toLocaleTimeString('ru-RU');if(sr.ok){let s=await sr.json(),online=!!s.ollama_online;if(lastOnline!==null&&online!==lastOnline)notice(online?'Ollama восстановлена':'Ollama недоступна');lastOnline=online;}}catch(e){status.textContent='Нет связи с источником метрик';}}
update();setInterval(update,6000);
window.NOXNotify=notice;
})();

'@,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText($widgetsCss,@'
/* Compact transparent brushed-metal telemetry, keeps center star open. */
#nox-live-widgets{position:fixed;right:12px;top:76px;z-index:45;width:min(318px,calc(100vw - 24px));color:#c9d1d8;background:linear-gradient(125deg,rgba(9,15,20,.55),rgba(27,33,38,.26));border:1px solid rgba(177,188,190,.15);border-radius:10px;box-shadow:inset 0 1px rgba(255,255,255,.075),0 9px 36px rgba(0,0,0,.18);backdrop-filter:blur(16px) saturate(.68);-webkit-backdrop-filter:blur(16px) saturate(.68);padding:9px 12px;font:11px/1.5 system-ui,sans-serif;pointer-events:auto}
.nox-monitor-head{display:flex;align-items:center;justify-content:space-between;letter-spacing:.17em;color:#a7b6b9}
#nox-notify-toggle{background:rgba(255,255,255,.045);border:1px solid rgba(255,255,255,.15);color:#cbd2d3;border-radius:7px;padding:3px 9px;cursor:pointer}
.nox-monitor-values{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:4px;margin-top:8px}
.nox-monitor-values span{min-width:0;white-space:nowrap;text-align:center;font-size:10px;color:#859496}
.nox-monitor-values b{display:block;color:#ecf0ef;font-weight:500;font-size:11px}
#nox-notice{margin-top:7px;color:#7f9296;font-size:10px}
#nox-alert-list{max-height:170px;overflow:auto;margin-top:7px;padding-top:5px;border-top:1px solid rgba(255,255,255,.12);color:#bec7c8}
#nox-alert-list>div{padding:4px 0;border-bottom:1px solid rgba(255,255,255,.045)}
@media(max-width:700px){#nox-live-widgets{top:auto;bottom:50px;right:5px;width:265px}.nox-monitor-values{grid-template-columns:repeat(3,1fr)}}

'@,[Text.UTF8Encoding]::new($false))
# Patch only the COPY, not existing NOX folders.
$serverFile=Join-Path $dest 'server.py'
$server=[IO.File]::ReadAllText($serverFile)
if(!$server.Contains('import pc_metrics')){$server="import pc_metrics`n"+$server}
$server=[regex]::Replace($server,'PORT\s*=\s*\d+','PORT=18771',1)
$token='    def do_GET(self):'
$inject="    def do_GET(self):`n        if self.path.split('?',1)[0]=='/api/pc-metrics':`n            return self._json(200,pc_metrics.read())"
if(!$server.Contains("'/api/pc-metrics'")){
 if(!$server.Contains($token)){throw 'Expected local server.py handler not found; abort without activating copy'}
 $server=$server.Replace($token,$inject)
}
[IO.File]::WriteAllText($serverFile,$server,[Text.UTF8Encoding]::new($false))
# Browser desktop notifications require user click. Never auto-request permission.
foreach($name in @('index.html','chat.html','training.html')){
 $path=Join-Path $dest $name
 if(!(Test-Path $path)){continue}
 $html=[IO.File]::ReadAllText($path)
 if(!$html.Contains('pc-widgets.js')){
   $mark='</body>'
   if(!$html.Contains($mark)){throw "No </body> in $name"}
   $html=$html.Replace($mark,'<link rel="stylesheet" href="./pc-widgets.css"><script src="./pc-widgets.js" defer></script></body>')
   [IO.File]::WriteAllText($path,$html,[Text.UTF8Encoding]::new($false))
 }
}
$galleryIndex=Join-Path $gallery 'index.html'
if(!(Test-Path $galleryIndex)){
  $links=@(
   @('blackhole/index.html','Black Hole · MIT · real WebGL'),
   @('../ready/sun.html','Three.js Lava Sun · original live source'),
   @('../ready/space.html','Three.js animated shader background'),
   @('../index.html','NOX HOME · live scene + widgets'),
   @('../chat.html','NOX CHAT · live Ollama'),
   @('../training.html','NOX TRAINING UI')
  )
  $a=($links|ForEach-Object {'<a href="'+$_[0]+'">'+$_[1]+'</a>'}) -join "`n"
  $page='<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>NOX · Original WOW Engines</title><style>body{background:#080a0d;color:#cdd5da;font:15px system-ui;margin:6vw}h1{font-weight:400;letter-spacing:.17em}a{display:block;color:#d9c2a3;text-decoration:none;border-bottom:1px solid #333;padding:16px 6px}a:hover{background:#192027}</style><h1>NOX · ORIGINAL WOW ENGINES</h1><p>Готовые исходники, проверка по одному. Никаких нарисованных сцен.</p>'+$a+'</html>'
  [IO.File]::WriteAllText($galleryIndex,$page,[Text.UTF8Encoding]::new($false))
}
$launcher=Join-Path $dest 'START_NOX_WEB.ps1'
if(Test-Path $launcher){
  $ps=[IO.File]::ReadAllText($launcher)
  $ps=[regex]::Replace($ps,'1876\d|18770','18771')
  [IO.File]::WriteAllText($launcher,$ps,[Text.UTF8Encoding]::new($false))
}
$manifest=[ordered]@{created=(Get-Date).ToString('o');source=$src;destination=$dest;downloaded=@($downloaded);reused=@($reused);failed=@($failed);gpu_metrics_source='nvidia-smi if installed';cpu_metrics_source='Win32_Processor LoadPercentage';ram_metrics_source='GlobalMemoryStatusEx';browser_notifications='on-click, while page open';no_models_or_SQLite_modified=$true}
$manifest | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $dest 'MEGA_DOWNLOAD_MANIFEST.json') -Encoding UTF8
$files=Get-ChildItem -LiteralPath $dest -Recurse -File -ErrorAction SilentlyContinue | Where-Object {$_.Extension -in @('.html','.js','.mjs','.css','.py')}
$hashes=$files | ForEach-Object {[pscustomobject]@{file=$_.FullName.Substring($dest.Length);sha256=(Get-FileHash $_.FullName -Algorithm SHA256).Hash}}
$hashes|ConvertTo-Json -Depth 4 | Set-Content (Join-Path $dest 'SHA256_DOWNLOADED_FILES.json') -Encoding UTF8
if(Get-Command python.exe -ErrorAction SilentlyContinue){& python.exe -m py_compile (Join-Path $dest 'pc_metrics.py') (Join-Path $dest 'server.py');if($LASTEXITCODE -ne 0){throw 'Python syntax verification failed'}}
Write-Host "`nNOX MEGA: downloaded $($downloaded.Count), reused $($reused.Count), optional failures $($failed.Count)" -ForegroundColor Green
Write-Host "Location: $dest" -ForegroundColor Cyan
Write-Host "Manifest: $(Join-Path $dest 'MEGA_DOWNLOAD_MANIFEST.json')"
if($failed.Count){Write-Warning 'Some OPTIONAL effects failed, see manifest. Site is preserved.'}
if(!(Test-Path (Join-Path $dest 'server.py'))){throw 'Server missing'}
if(!(Test-Path $launcher)){throw 'Launcher missing'}
# Launch the independent local site, do not kill or overwrite prior versions.
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $launcher
}