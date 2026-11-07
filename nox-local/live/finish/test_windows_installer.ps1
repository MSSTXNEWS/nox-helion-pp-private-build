# CI-only fixture: prove offline installer does not duplicate private data or use EXE.
# This fake base module exists in a disposable Windows runner, not in user build.
$ErrorActionPreference='Stop'
$root=Join-Path $env:RUNNER_TEMP ('NOX_WEB_CI_FIXTURE_'+[guid]::NewGuid().ToString('N'))
$src=Join-Path $root 'NOX_READY_01'
New-Item -ItemType Directory -Force -Path $src|Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $src 'vendor\tabler')|Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $src 'vendor\fx')|Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $src 'memory')|Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $src 'weights')|Out-Null
[IO.File]::WriteAllText((Join-Path $src 'vendor\tabler\tabler.min.css'),'body{color:white}')
[IO.File]::WriteAllText((Join-Path $src 'vendor\fx\echarts.min.js'),'window.echarts={};')
[IO.File]::WriteAllText((Join-Path $src 'memory\PRIVATE_OWNER.sqlite3'),'SENSITIVE_FIXTURE_MUST_NOT_COPY')
[IO.File]::WriteAllText((Join-Path $src 'weights\PRIVATE_OWNER.gguf'),'WEIGHT_FIXTURE_MUST_NOT_COPY')
[IO.File]::WriteAllText((Join-Path $src 'PRIVATE_OWNER.jsonl'),'LOG_FIXTURE_MUST_NOT_COPY')
@'
from http.server import SimpleHTTPRequestHandler
from urllib.parse import urlsplit
import json
PORT=18775
OLLAMA="http://127.0.0.1:11434"
def models():return []
class Handler(SimpleHTTPRequestHandler):
    def _json(self,status,value):
        data=json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def do_GET(self):
        if urlsplit(self.path).path=="/api/status":
            return self._json(200,{"models":[],"ollama_online":False})
        return super().do_GET()
    def do_POST(self):return self._json(404,{"error":"TEST_FIXTURE_ONLY"})
'@ | Set-Content -LiteralPath (Join-Path $src 'server.py') -Encoding UTF8
@'
def truth_metrics():return {"gpu_percent":None,"gpu_temperature_c":None}
def training_status():return {"status":"HOLD"}
def s03_status():return {"status":"HOLD","tables":[]}
def push_status():return {"webpush_server":"HOLD"}
def load_config():return {}
'@ | Set-Content -LiteralPath (Join-Path $src 'nox_services.py') -Encoding UTF8
@'
def add(value):return False
def send(*args):return {"status":"HOLD"}
class TrainerLogWatcher:
    def start(self):pass
'@ | Set-Content -LiteralPath (Join-Path $src 'nox_push.py') -Encoding UTF8
@'
def get():return {"status":"HOLD"}
'@ | Set-Content -LiteralPath (Join-Path $src 'pc_metrics.py') -Encoding UTF8
$kit=(Resolve-Path 'kit/NOX_WEB_11_22_SOURCE.zip').Path
$target=Join-Path $root 'NOX_LIVE'
$procId=$null
try{
 & './nox-local/live/finish/INSTALL_NOX_WEB_FROM_KIT.ps1' -Root $root -Kit $kit -NoBrowser
 if(!(Test-Path -LiteralPath (Join-Path $target 'server_live.py'))){throw 'WEB_INSTALL_SERVER_MISSING_HOLD'}
 foreach($p in @('memory\PRIVATE_OWNER.sqlite3','weights\PRIVATE_OWNER.gguf','PRIVATE_OWNER.jsonl')){
  if(Test-Path -LiteralPath (Join-Path $target $p)){throw "USER_PRIVATE_DATA_DUPLICATED_HOLD: $p"}
 }
 $health=Invoke-RestMethod 'http://127.0.0.1:18775/api/mega/health' -TimeoutSec 4
 if($health.identity -ne 'NOX_LOCAL_LIVE_V1' -or $health.releaseAccepted -ne $false){
   throw 'WEB_INSTALLED_HEALTH_NOT_EXACT_HOLD'
 }
 $connections=@(Get-NetTCPConnection -LocalPort 18775 -State Listen -ErrorAction SilentlyContinue)
 if($connections.Count -gt 0){$procId=[int]$connections[0].OwningProcess}
 Write-Host 'NOX_WEB_LOCAL_FIXTURE_INSTALL_LAUNCH_PASS (fake Ollama, S03, GPU remain HOLD)'
}finally{
 if($null -ne $procId){Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue}
}
