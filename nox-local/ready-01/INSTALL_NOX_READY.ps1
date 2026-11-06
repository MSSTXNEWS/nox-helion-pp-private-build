# NOX LOCAL READY INTEGRATION 01: existing ready engines only. ASCII source for Windows PowerShell 5.1.
& {
$ErrorActionPreference='Stop'
[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
$root='C:\NOX_HELION\APP\NOX_WEB'
$dest=Join-Path $root 'NOX_READY_01'
$src=$null
foreach($name in @('WOW_V7_FIXED','WOW_V7','WOW_V6','WOW_V5')){
 $path=Join-Path $root $name
 if((Test-Path (Join-Path $path 'server.py')) -and (Test-Path (Join-Path $path 'chat.html')) -and (Test-Path (Join-Path $path 'index.html'))){$src=$path;break}
}
if(!$src){throw 'Original NOX source missing. Existing NOX preserved.'}
if(Test-Path (Join-Path $dest 'READY_STAGE1.sha256')){
  $launch=Join-Path $dest 'START_NOX_READY.ps1'
  if(!(Test-Path $launch)){throw 'Existing NOX_READY_01 incomplete; preserved'}
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $launch
  return
}
if(Test-Path $dest){throw 'NOX_READY_01 already exists; refusing to overwrite'}
New-Item -ItemType Directory -Force -Path $root|Out-Null
Copy-Item -LiteralPath $src -Destination $dest -Recurse -ErrorAction Stop
$base='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build'
$uiCommit='cd56719ec64617d01e24e29bcc8c62859b1b92fe'
$functionsCommit='e001f9c5f3d8fc785175482cd4c1d679593b880f'
$hudCommit='785287af0bb08f77ef981ad0582b6bd9815ac67e'
function Receive-Source([string]$url,[string]$target,[int]$minimum){
  $parent=Split-Path -Parent $target
  New-Item -ItemType Directory -Force -Path $parent | Out-Null
  $part="$target.partial"
  try {
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $part -TimeoutSec 140 -ErrorAction Stop
    if((Get-Item -LiteralPath $part).Length -lt $minimum){throw "Incomplete file: $url"}
    Move-Item -LiteralPath $part -Destination $target -Force
  } finally { if(Test-Path $part){Remove-Item -LiteralPath $part -Force} }
}
# Reuse original V7 assets; only tested integration glue and original vendor files are added.
$ui=@('index.html','chat.html','training.html','nox.css','mega.css','cinema-hud.css','server_mega.py','START_NOX_READY.ps1','PROVENANCE_READY.md')
foreach($name in $ui){
  Receive-Source "$base/$uiCommit/nox-local/ready-01/$name" (Join-Path $dest $name) 400
}
$fn=@('nox_services.py','nox_push.py','mega-ui.js','sw.js','setup_vapid.py','nox_connections.example.json','chat-patched.js')
foreach($name in $fn){
 Receive-Source "$base/$functionsCommit/nox-local/functions-mega/$name" (Join-Path $dest $name) 140
}
Copy-Item -LiteralPath (Join-Path $dest 'chat-patched.js') -Destination (Join-Path $dest 'chat.js') -Force
Receive-Source "$base/$hudCommit/nox-local/cinema-hud/cinema-hud.js" (Join-Path $dest 'cinema-hud.js') 1800
Receive-Source "$base/$hudCommit/nox-local/cinema-hud/pc_metrics.py" (Join-Path $dest 'pc_metrics.py') 1100
# Original MIT Black Hole fully source-bound; no synthetic rings, shader or background.
$bh='https://raw.githubusercontent.com/sysscan/3d-blackhole-simulation/9cd793f34b972f6c8928b0d3127d94eff7613a61'
$black=Join-Path $dest 'vendor\blackhole'
New-Item -ItemType Directory -Force -Path $black|Out-Null
Receive-Source "$bh/index.html" (Join-Path $black 'SOURCE.html') 30000
Receive-Source "$bh/LICENSE" (Join-Path $black 'LICENSE') 900
Receive-Source 'https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js' (Join-Path $black 'three.min.js') 400000
function VerifyGitBlob([string]$path,[string]$expected){
 [byte[]]$data=[IO.File]::ReadAllBytes($path)
 [byte[]]$prefix=[Text.Encoding]::ASCII.GetBytes('blob '+$data.Length)
 [byte[]]$x=New-Object byte[] ($prefix.Length+1+$data.Length)
 [Array]::Copy($prefix,0,$x,0,$prefix.Length)
 [Array]::Copy($data,0,$x,$prefix.Length+1,$data.Length)
 $sha=[Security.Cryptography.SHA1]::Create()
 try{$actual=([BitConverter]::ToString($sha.ComputeHash($x))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}
 if($actual -ne $expected){throw "Pinned original Git source hash mismatch: $path"}
}
VerifyGitBlob (Join-Path $black 'SOURCE.html') 'baae2a37c851c73c6cf41039d000363d18e47643'
VerifyGitBlob (Join-Path $black 'LICENSE') 'd59de81c4eb387bba2a515b76a25944c59e5f83e'
$sourceHTML=[IO.File]::ReadAllText((Join-Path $black 'SOURCE.html'))
$needle='https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js'
if(!$sourceHTML.Contains($needle)){throw 'Black Hole source not recognized'}
$sourceHTML=$sourceHTML.Replace($needle,'./three.min.js')
$visualOnly='<style id="nox-original-scene-adaptation">#info,#controls,#title,#readout,#hud{display:none!important}html,body{background:transparent!important}canvas#gl{pointer-events:none!important}</style>'
$sourceHTML=$sourceHTML.Replace('</head>',$visualOnly+'</head>')
[IO.File]::WriteAllText((Join-Path $black 'sceneblackhole.html'),$sourceHTML,[Text.UTF8Encoding]::new($false))
# Verified ECharts dependency for the existing ready cinema speedometers.
$echarts=Join-Path $dest 'vendor\fx\echarts.min.js'
$old=Get-ChildItem -LiteralPath $root -Filter 'echarts.min.js' -File -Recurse -ErrorAction SilentlyContinue | Where-Object {$_.Length -gt 400000} | Select-Object -First 1
if($old){New-Item -ItemType Directory -Force -Path (Split-Path -Parent $echarts)|Out-Null;Copy-Item -LiteralPath $old.FullName -Destination $echarts}
else {Receive-Source 'https://cdn.jsdelivr.net/npm/echarts@5.6.0/dist/echarts.min.js' $echarts 400000}
# Export source ledger and never touch model/S03/training files.
$manifest=[ordered]@{version='NOX_READY_01';source=$src;destination=$dest;source_licenses=@('MIT Black Hole','MIT Three.js','Apache-2.0 ECharts');real_trainer='HOLD until contract verified';s03='READ_ONLY until schema verified';web_push='Available after local opt-in and VAPID';models_changed=$false;sqlite_changed=$false;time=(Get-Date).ToString('o');items=@()}
foreach($f in Get-ChildItem $dest -File -Recurse){$manifest.items+=@([ordered]@{path=$f.FullName.Substring($dest.Length+1);sha256=(Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash})}
$manifest | ConvertTo-Json -Depth 6 | Set-Content (Join-Path $dest 'NOX_READY_01_MANIFEST.json') -Encoding UTF8
$python=Get-Command python.exe -ErrorAction SilentlyContinue
if(!$python){throw 'Python 3 not installed; source ready but not started'}
& $python.Source -m py_compile (Join-Path $dest 'server_mega.py') (Join-Path $dest 'nox_services.py') (Join-Path $dest 'nox_push.py') (Join-Path $dest 'pc_metrics.py')
if($LASTEXITCODE -ne 0){throw 'Python validation failed; original unchanged'}
# Automatic installation of optional WebPush dependencies is isolated in NOX; no account keys leave this machine.
$target=Join-Path $dest 'PUSH_PACKAGES'
New-Item -ItemType Directory -Force -Path $target|Out-Null
try{
 & $python.Source -m pip install --disable-pip-version-check --target $target 'pywebpush>=2,<3' 'cryptography>=43,<47'
 if($LASTEXITCODE -eq 0){$env:PYTHONPATH=$target;& $python.Source (Join-Path $dest 'setup_vapid.py')}
}catch{Write-Warning 'Optional push dependencies incomplete; WebPush remains HOLD'}
# Explicit completed marker for next idempotent run.
(Get-FileHash (Join-Path $black 'SOURCE.html') -Algorithm SHA256).Hash | Set-Content (Join-Path $dest 'READY_STAGE1.sha256') -Encoding ASCII
Write-Host 'NOX READY: original live effects, original layout, Cinema HUD, Ollama, push code' -ForegroundColor Green
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $dest 'START_NOX_READY.ps1')
}