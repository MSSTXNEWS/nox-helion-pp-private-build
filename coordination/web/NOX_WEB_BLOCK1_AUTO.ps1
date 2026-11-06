& {
$ErrorActionPreference = 'Stop'
$ui = 'C:\NOX_HELION\APP\ui'
$index = Join-Path $ui 'menu-pages\index.html'
$menu = Join-Path $ui 'menu-pages\menu.js'
if (!(Test-Path -LiteralPath $index -PathType Leaf) -or !(Test-Path -LiteralPath $menu -PathType Leaf)) { throw "NOX WEB not found: $ui" }
$original = [IO.File]::ReadAllText($menu)
if (!$original.Contains('let client=null') -or !$original.Contains('const say=message=>') -or !$original.Contains('window.chrome?.webview')) { throw 'NOX WEB menu.js differs; original files not changed' }
$tags = Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 8
if (!($tags.models -is [array]) -or @($tags.models).Count -eq 0) { throw 'Local Ollama reports no installed models' }
Write-Host ('OLLAMA ONLINE | Models: ' + @($tags.models).Count) -ForegroundColor Green
$payload = @'
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
'@
$compressed = [Convert]::FromBase64String(($payload -replace '\s',''))
$stream = [IO.MemoryStream]::new($compressed)
$unzip = [IO.Compression.GZipStream]::new($stream,[IO.Compression.CompressionMode]::Decompress)
$buffer = [IO.MemoryStream]::new()
$unzip.CopyTo($buffer); $unzip.Dispose(); $stream.Dispose()
$bytes = $buffer.ToArray(); $buffer.Dispose()
$hashObj = [Security.Cryptography.SHA256]::Create()
$actual = ([BitConverter]::ToString($hashObj.ComputeHash($bytes))).Replace('-','').ToLowerInvariant()
$hashObj.Dispose()
if ($actual -ne 'a5496c7fc2b45b70597b21339583313dd677d23dfd0aa387f0b1c3e265bb24dc') { throw 'Embedded NOX WEB package corrupted; no files changed' }
$parts = [Text.Encoding]::UTF8.GetString($bytes) | ConvertFrom-Json
$base = Join-Path $env:LOCALAPPDATA 'NOX_HELION\WEB_BLOCK1'
New-Item -ItemType Directory -Path $base -Force | Out-Null
$bridge = Join-Path $base 'nox_web_local_server.py'
$client = Join-Path $base 'nox_web_browser_client.mjs'
$utf8 = [Text.UTF8Encoding]::new($false)
[IO.File]::WriteAllText($bridge,$parts.server,$utf8)
[IO.File]::WriteAllText($client,$parts.client,$utf8)
$pythonCandidates = @('C:\Program Files\Python312\python.exe',"$env:LOCALAPPDATA\Programs\Python\Python312\python.exe")
$cmd = Get-Command python.exe -ErrorAction SilentlyContinue
if ($cmd) { $pythonCandidates += $cmd.Source }
$python = $pythonCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1
if (!$python) { throw 'Python missing: your previous screenshot showed Python312; check installation' }
& $python -m py_compile $bridge
if ($LASTEXITCODE -ne 0) { throw 'NOX bridge syntax failed' }
$port = $null; $existing = $false
foreach ($candidate in 18765..18774) {
  $addr = "http://127.0.0.1:$candidate"
  try { $status = Invoke-RestMethod "$addr/nox-api/status" -TimeoutSec 1; if ($status.service -eq 'NOX_WEB_LOCAL_BRIDGE_1') { $port=$candidate; $existing=$true; break } } catch {}
  $sock = [Net.Sockets.TcpClient]::new()
  $occupied = $false
  try { $sock.Connect('127.0.0.1',$candidate); $occupied=$true } catch {} finally { $sock.Dispose() }
  if (!$occupied) { $port=$candidate; break }
}
if ($null -eq $port) { throw 'Ports 18765-18774 occupied; no unrelated process stopped' }
if (!$existing) {
  $log = Join-Path $base "server-$port.log"; $err = Join-Path $base "server-$port-errors.log"
  $argsList = @('-u',('"'+$bridge+'"'),('"'+$ui+'"'),('"'+$client+'"'),[string]$port)
  $proc = Start-Process -FilePath $python -ArgumentList $argsList -WorkingDirectory $base -WindowStyle Hidden -RedirectStandardOutput $log -RedirectStandardError $err -PassThru
}
$url = "http://127.0.0.1:$port/menu-pages/index.html"
$ready = $false
for ($i=0; $i -lt 24; $i++) {
  try { $s = Invoke-RestMethod "http://127.0.0.1:$port/nox-api/status" -TimeoutSec 2; if ($s.service -eq 'NOX_WEB_LOCAL_BRIDGE_1' -and $s.ollama_online) { $ready=$true; break } } catch {}
  Start-Sleep -Milliseconds 500
}
if (!$ready) { throw "NOX bridge not ready. Check $base logs; original NOX files remain unchanged" }
Write-Host "NOX WEB + LIVE LOCAL AI: $url" -ForegroundColor Green
Write-Host 'Streaming and STOP active; original SQLite/S03 unchanged' -ForegroundColor Cyan
Start-Process $url
}