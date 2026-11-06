& {
$ErrorActionPreference='Stop'
$root='C:\NOX_HELION\APP\NOX_WEB'
$dest=Join-Path $root 'WOW_V7'
$start=Join-Path $dest 'START_NOX_WEB.ps1'
$commit='49ab5be70757f55c2ae9e9b19c10a8b4b850229b'
$up="https://raw.githubusercontent.com/mrdoob/three.js/$commit/examples"
function Get-NoxOfficial([string]$relative,[string]$local) {
  $parent=Split-Path -Parent $local
  New-Item -ItemType Directory -Force -Path $parent | Out-Null
  Invoke-WebRequest -UseBasicParsing -Uri "$up/$relative" -OutFile $local -ErrorAction Stop
  if((Get-Item -LiteralPath $local).Length -eq 0){throw "Official source empty: $relative"}
}
if(!(Test-Path -LiteralPath $start)) {
  if(Test-Path -LiteralPath $dest){throw 'WOW_V7 folder exists but is incomplete; left unchanged'}
  $candidates=@(Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -like 'WOW_V6*' -and (Test-Path (Join-Path $_.FullName 'server.py')) -and (Test-Path (Join-Path $_.FullName 'main.mjs')) })
  if(!$candidates.Count){throw 'Cannot find existing WOW_V6; existing files left unchanged'}
  $source=($candidates|Sort-Object LastWriteTime -Descending|Select-Object -First 1).FullName
  Write-Host "Reusing existing NOX: $source" -ForegroundColor Cyan
  Copy-Item -LiteralPath $source -Destination $dest -Recurse -ErrorAction Stop
  $ready=Join-Path $dest 'ready'
  New-Item -ItemType Directory -Force -Path $ready | Out-Null
  Get-NoxOfficial 'webgl_shader_lava.html' (Join-Path $ready 'sun.html')
  Get-NoxOfficial 'webgl_shader.html' (Join-Path $ready 'space.html')
  Get-NoxOfficial 'textures/lava/cloud.png' (Join-Path $ready 'textures\lava\cloud.png')
  Get-NoxOfficial 'textures/lava/lavatile.jpg' (Join-Path $ready 'textures\lava\lavatile.jpg')
  Get-NoxOfficial 'jsm/postprocessing/BloomPass.js' (Join-Path $dest 'vendor\three\addons\postprocessing\BloomPass.js')
  Get-NoxOfficial 'jsm/shaders/ConvolutionShader.js' (Join-Path $dest 'vendor\three\addons\shaders\ConvolutionShader.js')
  foreach($name in @('sun.html','space.html')){
    $p=Join-Path $ready $name
    $s=[IO.File]::ReadAllText($p)
    $s=[regex]::Replace($s,'(?s)<div id="info">.*?</div>','')
    $s=$s.Replace('<link type="text/css" rel="stylesheet" href="main.css">','<style>html,body{margin:0;width:100%;height:100%;overflow:hidden;background:transparent}#container{position:fixed;inset:0}#container canvas{display:block;width:100%;height:100%}</style>')
    $s=$s.Replace('"three": "../build/three.module.js"','"three": "../vendor/three/three.module.js"')
    $s=$s.Replace('"three/addons/": "./jsm/"','"three/addons/": "../vendor/three/addons/"')
    if($name -eq 'sun.html'){
      $s=$s.Replace('new THREE.TorusGeometry( size, 0.3, 30, 30 )','new THREE.SphereGeometry( size * 1.60, 96, 64 )')
      $s=$s.Replace('new BloomPass( 1.25 )','new BloomPass( 0.32 )')
      $s=$s.Replace('camera.position.z = 4;','camera.position.z = 3.6;')
      $s=$s.Replace('renderer.autoClear = false;','renderer.autoClear = true; renderer.setClearColor( 0x000000, 0 );')
      $s=$s.Replace('renderer.setPixelRatio( window.devicePixelRatio );','renderer.setPixelRatio( Math.min( window.devicePixelRatio, 1.4 ) );')
    }else{
      $s=$s.Replace('renderer = new THREE.WebGLRenderer();','renderer = new THREE.WebGLRenderer({alpha:true,antialias:false,powerPreference:"low-power"});')
      $s=$s.Replace('renderer.setPixelRatio( window.devicePixelRatio );','renderer.setPixelRatio( Math.min( window.devicePixelRatio, 0.9 ) );')
      $s=$s.Replace('uniforms[ ''time'' ].value = performance.now() / 1000;','if(performance.now()-(window.__noxLastFrame||0)<48)return;window.__noxLastFrame=performance.now(); uniforms[ ''time'' ].value = performance.now() / 1000;')
    }
    [IO.File]::WriteAllText($p,$s,[Text.UTF8Encoding]::new($false))
  }
  $htmlPath=Join-Path $dest 'index.html'
  $html=[IO.File]::ReadAllText($htmlPath)
  $old='<div id="glstage" aria-hidden="true"></div>'
  if(!$html.Contains($old)){throw 'Original V6 stage markup not found; stop before modifications'}
  $html=$html.Replace($old,'<div id="spaceBackdrop" aria-hidden="true"><iframe title="Official animated Three.js background" src="./ready/space.html" tabindex="-1"></iframe></div><div id="glstage" aria-hidden="true"><iframe title="Official animated Three.js sun" src="./ready/sun.html" tabindex="-1"></iframe></div>')
  $html=$html.Replace('<script type="module" src="./main.mjs"></script>','<script type="module" src="./main-v7.mjs"></script>')
  $html=$html.Replace('THREE.JS / SOURCE LAVA / CORONA','THREE.JS / TWO ORIGINAL ANIMATED SOURCES')
  [IO.File]::WriteAllText($htmlPath,$html,[Text.UTF8Encoding]::new($false))
  $main=[IO.File]::ReadAllText((Join-Path $dest 'main.mjs'))
  $main=$main.Replace("import { initHelion } from './scene.mjs';","import { initHelion } from './ready/adapter.mjs';")
  [IO.File]::WriteAllText((Join-Path $dest 'main-v7.mjs'),$main,[Text.UTF8Encoding]::new($false))
  $adapter=@'
export function initHelion(container,{onFPS=()=>{}}={}){
  let mode='MAX';
  return {ok:true,focus(){},setMode(m){mode=m;container.style.opacity=mode==='ECO'?'0.42':mode==='BALANCED'?'0.7':'0.92';const bg=document.querySelector('#spaceBackdrop');if(bg)bg.style.display=mode==='ECO'?'none':'';},destroy(){}};
}
'@
  [IO.File]::WriteAllText((Join-Path $ready 'adapter.mjs'),$adapter,[Text.UTF8Encoding]::new($false))
  $css=@'
/* Original downloaded animated Three.js examples, no static painted background */
#spaceBackdrop{position:absolute;inset:0;z-index:0;overflow:hidden;pointer-events:none;opacity:.13;filter:saturate(.35) contrast(1.2) brightness(.46);mask-image:linear-gradient(90deg,#000 0%,transparent 35%,transparent 65%,#000 100%)}
#spaceBackdrop iframe{width:100%;height:100%;border:0;pointer-events:none}
#glstage{position:absolute;inset:0;z-index:1;pointer-events:none;opacity:.92;filter:saturate(.76) contrast(1.07) brightness(.65)}
#glstage iframe{width:100%;height:100%;border:0;pointer-events:none}
body.nox-home .fallback-orb{display:none!important}
.hero-ui{z-index:5}
@media(prefers-reduced-motion:reduce){#spaceBackdrop{display:none}#glstage{filter:grayscale(.8) brightness(.35)}}
'@
  Add-Content -LiteralPath (Join-Path $dest 'nox.css') -Value $css -Encoding UTF8
  foreach($p in @('server.py','START_NOX_WEB.ps1')){
    $f=Join-Path $dest $p
    $s=[IO.File]::ReadAllText($f).Replace('18768','18769').Replace('V6 running','V7 running')
    [IO.File]::WriteAllText($f,$s,[Text.UTF8Encoding]::new($false))
  }
  [IO.File]::WriteAllText((Join-Path $ready 'ORIGINAL_SOURCES.txt'),"Three.js pinned commit $commit. Official complete demos: webgl_shader_lava.html + webgl_shader.html and 2 original textures. Their shader GLSL is unchanged. License: MIT, vendor/three/LICENSE.",[Text.UTF8Encoding]::new($false))
}
if(!(Test-Path -LiteralPath (Join-Path $dest 'ready\sun.html'))){throw 'Sun source missing'}
if(!(Test-Path -LiteralPath (Join-Path $dest 'ready\space.html'))){throw 'Animated background source missing'}
Write-Host "NOX V7: prebuilt animated sun + downloaded live background, all local" -ForegroundColor Green
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $start
}