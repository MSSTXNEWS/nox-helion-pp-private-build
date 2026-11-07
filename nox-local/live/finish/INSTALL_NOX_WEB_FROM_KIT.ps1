# NOX WEB 11–22: verified local overlay into existing NOX_READY_01.
# Safe create-only install: NEVER overwrite NOX_LIVE, models, SQLite, trainers or port 18774.
[CmdletBinding()]
param(
  [string]$Root='C:\NOX_HELION\APP\NOX_WEB',
  [string]$Kit=(Join-Path $PSScriptRoot 'NOX_WEB_11_22_SOURCE.zip'),
  [switch]$NoBrowser
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
$source=Join-Path $Root 'NOX_READY_01'
$target=Join-Path $Root 'NOX_LIVE'
$stage=Join-Path $Root ('_NOX_LIVE_11_22_STAGE_'+[guid]::NewGuid().ToString('N'))
if(Test-Path -LiteralPath $target){throw "NOX_LIVE_EXISTS_NO_OVERWRITE_HOLD: $target (existing version preserved)"}
if(!(Test-Path -LiteralPath $Kit -PathType Leaf)){throw "WEB_KIT_NOT_FOUND_HOLD: $Kit"}
foreach($f in @('server.py','vendor\tabler\tabler.min.css','vendor\fx\echarts.min.js')){
 if(!(Test-Path -LiteralPath (Join-Path $source $f) -PathType Leaf)){
  throw "ORIGINAL_NOX_READY_01_SOURCE_MISSING_HOLD: $f"
 }
}
if(Get-NetTCPConnection -LocalPort 18775 -State Listen -ErrorAction SilentlyContinue){
 throw 'WEB_PORT_18775_ALREADY_OCCUPIED_HOLD: existing process untouched'
}
$python=Get-Command python.exe -ErrorAction SilentlyContinue
if(!$python){throw 'PYTHON_NOT_INSTALLED_HOLD: no auto-install of runtime'}
Add-Type -AssemblyName System.IO.Compression.FileSystem
$z=[IO.Compression.ZipFile]::OpenRead((Resolve-Path -LiteralPath $Kit).Path)
try{
 $names=@($z.Entries|ForEach-Object{$_.FullName})
 if($names.Count -ne 31 -or ($names|Sort-Object -Unique).Count -ne 31){
  throw 'WEB_ZIP_FILE_COUNT_OR_DUPLICATE_HOLD'
 }
 foreach($name in $names){
  if($name.StartsWith('/') -or $name.StartsWith('.') -or $name -match '(^[A-Za-z]:)|\.\.|\\|[:<>"|?*]' -or $name.EndsWith('/')){
   throw "WEB_ZIP_UNSAFE_PATH_HOLD: $name"
  }
 }
}finally{$z.Dispose()}
Copy-Item -LiteralPath $source -Destination $stage -Recurse -ErrorAction Stop
$overlay=Join-Path $stage '_WEB_SOURCE_OVERLAY'
New-Item -ItemType Directory -Path $overlay -Force|Out-Null
[IO.Compression.ZipFile]::ExtractToDirectory((Resolve-Path -LiteralPath $Kit).Path,$overlay)
$mf=Join-Path $overlay 'NOX_WEB_STAGED_MANIFEST.json'
if(!(Test-Path -LiteralPath $mf)){throw 'WEB_MANIFEST_MISSING_HOLD'}
$manifest=Get-Content -LiteralPath $mf -Raw -Encoding UTF8|ConvertFrom-Json
if($manifest.schema -ne 'NOX_WEB_11_22_STAGED_V1' -or @($manifest.files).Count -ne 30){
 throw 'WEB_MANIFEST_SCHEMA_OR_FILE_COUNT_HOLD'
}
foreach($f in $manifest.files){
 $name=[string]$f.name
 if($name -match '(^[./\\])|(^[A-Za-z]:)|\.\.|[:<>"|?*]'){throw "WEB_MANIFEST_UNSAFE_PATH_HOLD: $name"}
 $src=Join-Path $overlay $name
 if(!(Test-Path -LiteralPath $src -PathType Leaf)){throw "WEB_PATCH_FILE_MISSING_HOLD: $name"}
 $actual=(Get-FileHash -LiteralPath $src -Algorithm SHA256).Hash
 if($actual -ne ([string]$f.sha256).ToUpperInvariant()){throw "WEB_PATCH_SHA_HOLD: $name"}
 if((Get-Item -LiteralPath $src).Length -ne [int64]$f.bytes){throw "WEB_PATCH_LENGTH_HOLD: $name"}
 $dest=Join-Path $stage $name
 $parent=Split-Path -Parent $dest
 New-Item -ItemType Directory -Force -Path $parent|Out-Null
 Copy-Item -LiteralPath $src -Destination $dest -Force
 if((Get-FileHash -LiteralPath $dest -Algorithm SHA256).Hash -ne $actual){throw "WEB_PATCH_READBACK_HOLD: $name"}
}
# The original MIT shader and license are bundled with exact blob provenance.
# No network downloads or static substitutions are necessary.
$shader=Join-Path $stage 'vendor\radiant\eclipse-glow.html'
$sourceShader=Join-Path $stage 'vendor\radiant\SOURCE-eclipse-glow.html'
$license=Join-Path $stage 'vendor\radiant\LICENSE'
foreach($p in @($shader,$sourceShader,$license)){
 if(!(Test-Path -LiteralPath $p -PathType Leaf)){throw "WEB_PINNED_SHADER_FILE_MISSING_HOLD: $p"}
}
if(-not ([IO.File]::ReadAllText($license)).StartsWith('MIT License')){throw 'SHADER_LICENSE_HOLD'}
if(-not ([IO.File]::ReadAllText($sourceShader)).Contains('<div class="label">Eclipse Glow</div>')){
 throw 'SHADER_ORIGINAL_SOURCE_ID_HOLD'
}
if(!(Test-Path -LiteralPath $shader -PathType Leaf)){
 $shaderDir=Split-Path -Parent $shader
 New-Item -ItemType Directory -Path $shaderDir -Force|Out-Null
 $raw='https://raw.githubusercontent.com/pbakaus/radiant/59e9f48c0ad9a3db2fbeb8898b4390d5a1eabb40'
 $orig=Join-Path $shaderDir 'SOURCE-eclipse-glow.html'
 $license=Join-Path $shaderDir 'LICENSE'
 Invoke-WebRequest -UseBasicParsing "$raw/static/eclipse-glow.html" -OutFile $orig -TimeoutSec 90
 Invoke-WebRequest -UseBasicParsing "$raw/LICENSE" -OutFile $license -TimeoutSec 90
 function GitBlobHash([string]$p){
  [byte[]]$b=[IO.File]::ReadAllBytes($p)
  [byte[]]$head=[Text.Encoding]::ASCII.GetBytes('blob '+$b.Length)
  [byte[]]$all=New-Object byte[] ($head.Length+1+$b.Length)
  [Array]::Copy($head,0,$all,0,$head.Length)
  [Array]::Copy($b,0,$all,$head.Length+1,$b.Length)
  $h=[Security.Cryptography.SHA1]::Create()
  try{return ([BitConverter]::ToString($h.ComputeHash($all))).Replace('-','').ToLowerInvariant()}
  finally{$h.Dispose()}
 }
 if((GitBlobHash $orig) -ne 'ef61254ca3b19830d8be6bf960e957ed613f69b0' -or
    (GitBlobHash $license) -ne '3e54c0daeb1d1a0c462019e6fd3e96cc82651daf'){
  throw 'PINNED_ORIGINAL_SHADER_OR_LICENSE_HOLD'
 }
 if(-not ([IO.File]::ReadAllText($license)).StartsWith('MIT License')){throw 'SHADER_LICENSE_HOLD'}
 $gl=[IO.File]::ReadAllText($orig)
 if(-not $gl.Contains('<div class="label">Eclipse Glow</div>')){throw 'SHADER_SOURCE_ID_HOLD'}
 [IO.File]::WriteAllText($shader,$gl.Replace('<div class="label">Eclipse Glow</div>',''),[Text.UTF8Encoding]::new($false))
}
if(!(Test-Path -LiteralPath $shader -PathType Leaf) -or (Get-Item $shader).Length -lt 14000){
 throw 'WEBGL_SCENE_SOURCE_MISSING_HOLD'
}
Remove-Item -LiteralPath $overlay -Recurse -Force
& $python.Source -m py_compile (Join-Path $stage 'server_live.py') (Join-Path $stage 'server.py')
if($LASTEXITCODE -ne 0){throw 'WEB_PYTHON_COMPILE_HOLD'}
Push-Location $stage
try{
 & $python.Source -m unittest discover -s tests -p test_live.py -q
 if($LASTEXITCODE -ne 0){throw 'ORIGINAL_WEB_CONTRACT_HOLD'}
}finally{Pop-Location}
$receipt=[ordered]@{
 schema='NOX_WEB_11_22_INSTALLED_SOURCE_V1'
 instructions_version='0.0.6'
 source_path=$source
 source_kit_sha256=(Get-FileHash -LiteralPath $Kit -Algorithm SHA256).Hash
 state='SOURCE_PREPARED_WINDOWS_RUNTIME_PENDING'
 ownerQwenStopSqlite='NOT_TESTED'
 gpuTraining='HOLD_SAFE70'
 webVoice='NOT_TESTED'
 memoryS03='ORIGINAL_UNCHANGED'
 releaseAccepted=$false
}
$receipt|ConvertTo-Json|Set-Content -LiteralPath (Join-Path $stage 'NOX_WEB_11_22_RECEIPT.json') -Encoding UTF8
if(Test-Path -LiteralPath $target){throw 'CONCURRENT_NOX_LIVE_INSTALL_HOLD'}
Move-Item -LiteralPath $stage -Destination $target
Write-Host "NOX WEB files prepared in $target (original preserved)" -ForegroundColor Green
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'START_NOX_WEB.ps1') -Root $Root -NoBrowser:$NoBrowser
