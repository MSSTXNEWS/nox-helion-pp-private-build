# NOX LOCAL LIVE - pinned, repeatable one-shot source integration for Windows PowerShell 5.1.
# instructions_version 0.0.6. Never modifies weights, Ollama, SQLite, trainer, older NOX web versions.
& {
  $ErrorActionPreference = 'Stop'
  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
  $root = 'C:\NOX_HELION\APP\NOX_WEB'
  $source = Join-Path $root 'NOX_READY_01'
  $target = Join-Path $root 'NOX_LIVE'
  $payloadCommit = '06aba53128f286ddada19933c733ac42844b8692'
  $payloadSha = '1401155AF09B48520EBE8614E8105136A8AA32DD0A43A45C12183B41AF52BE47'
  $payloadUrl = "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/$payloadCommit/nox-local/live/NOX_LIVE_PAYLOAD.json"
  if (!(Test-Path (Join-Path $source 'server.py'))) { throw 'Existing source NOX_READY_01/server.py not found. Original NOX untouched.' }
  if (!(Test-Path (Join-Path $source 'vendor\tabler\tabler.min.css'))) { throw 'Original Tabler source missing. Original NOX untouched.' }
  if (!(Test-Path (Join-Path $source 'vendor\fx\echarts.min.js'))) { throw 'Original ECharts source missing. Original NOX untouched.' }
  if (Test-Path $target) {
    $receipt = Join-Path $target 'NOX_LIVE_RECEIPT.json'
    if (!(Test-Path $receipt)) { throw 'Existing NOX_LIVE has no verified receipt. Refusing to overwrite.' }
    $state = Get-Content -LiteralPath $receipt -Raw | ConvertFrom-Json
    if ($state.payload_sha256 -ne $payloadSha) { throw 'Existing NOX_LIVE has a different version. Refusing to overwrite.' }
    Write-Host 'NOX LIVE already installed; starting existing verified version.' -ForegroundColor Cyan
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $target 'START_NOX_LIVE.ps1')
    return
  }
  New-Item -ItemType Directory -Force -Path $root | Out-Null
  $stage = Join-Path $root ('_NOX_LIVE_INSTALL_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
  if (Test-Path $stage) { throw 'Installation stage already exists' }
  Copy-Item -LiteralPath $source -Destination $stage -Recurse -ErrorAction Stop
  Write-Host 'NOX: using original local sources without downloads folder.' -ForegroundColor Cyan
  function Download-Complete([string]$url,[string]$path,[int]$minimum) {
    $dir = Split-Path -Parent $path
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $part = $path + '.partial'
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $part -ErrorAction Stop -TimeoutSec 90
    if ((Get-Item -LiteralPath $part).Length -lt $minimum) { throw "Incomplete download: $url" }
    Move-Item -LiteralPath $part -Destination $path -Force
  }
  function Verify-Blob([string]$file,[string]$expected) {
    [byte[]]$body = [IO.File]::ReadAllBytes($file)
    [byte[]]$prefix = [Text.Encoding]::ASCII.GetBytes(('blob ' + $body.Length))
    [byte[]]$raw = New-Object byte[] ($prefix.Length + 1 + $body.Length)
    [Array]::Copy($prefix,0,$raw,0,$prefix.Length)
    [Array]::Copy($body,0,$raw,$prefix.Length+1,$body.Length)
    $sha = [Security.Cryptography.SHA1]::Create()
    try { $actual = ([BitConverter]::ToString($sha.ComputeHash($raw))).Replace('-','').ToLowerInvariant() }
    finally { $sha.Dispose() }
    if ($actual -ne $expected) { throw "Pinned original source SHA mismatch: $file" }
  }
  $bundle = Join-Path $stage 'NOX_LIVE_PAYLOAD.json'
  Download-Complete $payloadUrl $bundle 120000
  if ((Get-FileHash -LiteralPath $bundle -Algorithm SHA256).Hash -ne $payloadSha) { throw 'NOX source payload SHA256 mismatch: installation stopped.' }
  $json = Get-Content -LiteralPath $bundle -Raw -Encoding UTF8 | ConvertFrom-Json
  if ($json.schema -ne 'NOX_SOURCE_PAYLOAD_V1') { throw 'Unknown payload schema' }
  foreach ($asset in $json.files) {
    $name = [string]$asset.name
    if ($name -match '(^[./\\])|(^[A-Za-z]:)|\.\.|[<>:"|?*]') { throw "Unsafe relative file path: $name" }
    $output = Join-Path $stage $name
    $dir = Split-Path -Parent $output
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    [byte[]]$bytes = [Convert]::FromBase64String([string]$asset.base64)
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $sum = ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-','') }
    finally { $sha.Dispose() }
    if ($sum -ne ([string]$asset.sha256)) { throw "Source verification failed: $name" }
    [IO.File]::WriteAllBytes($output,$bytes)
  }
  # Download exactly ONE complete pre-existing MIT shader. Keep its unmodified original.
  $radiant = 'https://raw.githubusercontent.com/pbakaus/radiant/59e9f48c0ad9a3db2fbeb8898b4390d5a1eabb40'
  $v = Join-Path $stage 'vendor\radiant'
  New-Item -ItemType Directory -Force $v | Out-Null
  $original = Join-Path $v 'SOURCE-eclipse-glow.html'
  $license = Join-Path $v 'LICENSE'
  Download-Complete "$radiant/static/eclipse-glow.html" $original 14000
  Download-Complete "$radiant/LICENSE" $license 1000
  Verify-Blob $original 'ef61254ca3b19830d8be6bf960e957ed613f69b0'
  Verify-Blob $license '3e54c0daeb1d1a0c462019e6fd3e96cc82651daf'
  if (!([IO.File]::ReadAllText($license).StartsWith('MIT License'))) { throw 'Radiant license not verified' }
  $eclipse = [IO.File]::ReadAllText($original)
  if (!$eclipse.Contains('<div class="label">Eclipse Glow</div>')) { throw 'Unexpected eclipse source' }
  # Keep original GLSL and animation untouched; hide only the demo label to display NOX UI.
  $eclipse = $eclipse.Replace('<div class="label">Eclipse Glow</div>','')
  [IO.File]::WriteAllText((Join-Path $v 'eclipse-glow.html'),$eclipse,[Text.UTF8Encoding]::new($false))
  # Safeguard model history, S03 and locally generated VAPID configuration from the original folder.
  $python = Get-Command python.exe -ErrorAction SilentlyContinue
  if (!$python) { throw 'Existing Python runtime not found. No change to active NOX.' }
  & $python.Source -m py_compile (Join-Path $stage 'server_live.py') (Join-Path $stage 'server.py') (Join-Path $stage 'pc_metrics.py') (Join-Path $stage 'nox_services.py')
  if ($LASTEXITCODE -ne 0) { throw 'Python syntax preflight failed' }
  $test = Join-Path $stage 'tests\test_live.py'
  if (!(Test-Path $test)) { throw 'NOX contract tests missing' }
  Push-Location $stage
  try {
    & $python.Source -m unittest discover -s tests -p test_live.py -q
    if ($LASTEXITCODE -ne 0) { throw 'NOX API preflight tests failed' }
  } finally { Pop-Location }
  $receipt = [ordered]@{
    instructions_version='0.0.6';release='NOX_LIVE';installed_at=(Get-Date).ToString('o')
    source_path=$source;payload_sha256=$payloadSha;radiant_commit='59e9f48c0ad9a3db2fbeb8898b4390d5a1eabb40'
    visual_scene='Radiant Eclipse Glow / MIT';chat_backend='Existing Ollama localhost'
    s03_writes='HOLD until exact original schema and owner approval';trainer_start='HOLD until verified original trainer'
    windows_visual_acceptance='NOT_VERIFIED';web_push_close_tab='NOT_VERIFIED';status='SOURCE_TESTS_PASS_WINDOWS_PENDING'
  }
  $receipt | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $stage 'NOX_LIVE_RECEIPT.json') -Encoding UTF8
  Move-Item -LiteralPath $stage -Destination $target -ErrorAction Stop
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $target 'DISCOVER_NOX.ps1')
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $target 'START_NOX_LIVE.ps1')
}