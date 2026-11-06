& {
  $ErrorActionPreference = 'Stop'
  $root = 'C:\NOX_HELION'
  $web = Join-Path $root 'APP\NOX_WEB'
  $assets = Join-Path $web 'assets'
  $logs = Join-Path $root 'LOGS\WEB'
  foreach ($folder in @($web,$assets,$logs)) {
    New-Item -ItemType Directory -Path $folder -Force | Out-Null
  }
  $sourceOptions = @(
    (Get-ChildItem -LiteralPath (Join-Path $root 'APP\work\source\assets\visual_pack') -File -Filter 'NOX_HELION_HOME_CURRENT_OWNER_APPROVED*.png' -ErrorAction SilentlyContinue),
    (Get-Item -LiteralPath (Join-Path $root 'APP\work\source\assets\HOME_OWNER_APPROVED.png') -ErrorAction SilentlyContinue),
    (Get-Item -LiteralPath (Join-Path $root 'APP\coordination\mega814\approved_persona\NOX_HELION_HOME_OWNER_APPROVED_20261019.png') -ErrorAction SilentlyContinue)
  ) | Where-Object { $_ -and $_.Length -gt 500000 } | Select-Object -First 1
  if (!$sourceOptions) { throw 'APPROVED_D02_PNG_NOT_FOUND: NOX sources preserved' }
  $approved = $sourceOptions.FullName
  $target = Join-Path $assets 'home-approved.png'
  $sourceHash = (Get-FileHash -LiteralPath $approved -Algorithm SHA256).Hash
  if (!(Test-Path -LiteralPath $target) -or (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $sourceHash) {
    if (Test-Path -LiteralPath $target) {
      $backup = Join-Path $web ('home-approved.backup.' + (Get-Date -Format 'yyyyMMddHHmmss') + '.png')
      Copy-Item -LiteralPath $target -Destination $backup -ErrorAction Stop
    }
    Copy-Item -LiteralPath $approved -Destination $target -ErrorAction Stop
  }
  if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $sourceHash) { throw 'D02_APPROVED_IMAGE_SHA_MISMATCH' }
  $tags = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 10 -ErrorAction Stop
  $installed = @($tags.models | Where-Object { $_ -and $_.name })
  if (!$installed.Count) { throw 'OLLAMA_INSTALLED_MODELS_NOT_VISIBLE' }
  $pythonCandidates = @('C:\Program Files\Python312\python.exe',"$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",(Get-Command python.exe -ErrorAction SilentlyContinue).Source)
  $python = $pythonCandidates | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -First 1
  if (!$python) { throw 'PYTHON_NOT_FOUND' }
  $utf8 = New-Object System.Text.UTF8Encoding($false)
  $serverFile = Join-Path $web 'nox_web_server.py'
  $htmlFile = Join-Path $web 'index.html'
  $serverCode = @'
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib import request as ur, error as ue
from pathlib import Path
import json, secrets, sys, threading

ROOT = Path(sys.argv[1]).resolve()
PORT = int(sys.argv[2])
TOKEN = secrets.token_urlsafe(32)
ACTIVE = {}
LOCK = threading.RLock()
LIMIT = 200000

class NoRedirect(ur.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('OLLAMA_REDIRECT_DENIED')

opener = ur.build_opener(ur.ProxyHandler({}), NoRedirect())

def models():
    with opener.open('http://127.0.0.1:11434/api/tags', timeout=8) as res:
        data = json.loads(res.read(2_000_000))
    return sorted({str(m['name']) for m in data.get('models', []) if isinstance(m, dict) and isinstance(m.get('name'), str) and 0 < len(m['name']) < 161})

class Web(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print(fmt % args, flush=True)

    def headers_safe(self):
        host = self.headers.get('Host', '').lower()
        if host not in (f'127.0.0.1:{PORT}', f'localhost:{PORT}'):
            self.send_error(403)
            return False
        return True

    def reply(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self.headers_safe(): return
        if self.path in ('/', '/index.html'):
            file, typ = ROOT / 'index.html', 'text/html; charset=utf-8'
        elif self.path == '/assets/home-approved.png':
            file, typ = ROOT / 'assets' / 'home-approved.png', 'image/png'
        elif self.path == '/api/session':
            try: self.reply(200, {'token': TOKEN, 'models': models(), 'status': 'OLLAMA_CONNECTED'})
            except Exception as e: self.reply(503, {'status': 'OLLAMA_OFFLINE', 'error': type(e).__name__})
            return
        else:
            self.send_error(404)
            return
        if not file.is_file(): self.send_error(404); return
        self.send_response(200)
        self.send_header('Content-Type', typ)
        self.send_header('Content-Length', str(file.stat().st_size))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        with file.open('rb') as f:
            while chunk := f.read(65536): self.wfile.write(chunk)

    def do_POST(self):
        if not self.headers_safe(): return
        origin = self.headers.get('Origin')
        if origin and origin not in (f'http://127.0.0.1:{PORT}', f'http://localhost:{PORT}'):
            self.reply(403, {'error':'ORIGIN_DENIED'}); return
        if self.headers.get('X-NOX-Token') != TOKEN or self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            self.reply(403, {'error':'LOCAL_SESSION_DENIED'}); return
        try:
            length = int(self.headers.get('Content-Length','0'))
            if not 0 < length <= LIMIT: raise ValueError()
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict): raise ValueError()
        except Exception:
            self.reply(400, {'error':'BAD_REQUEST'}); return
        if self.path == '/api/stop':
            ident = data.get('id')
            with LOCK:
                task = ACTIVE.get(ident)
            if not task:
                self.reply(409, {'stopped':False}); return
            task['stop'].set()
            upstream = task.get('upstream')
            if upstream is not None:
                threading.Thread(target=upstream.close, daemon=True).start()
            self.reply(200, {'stopped':True}); return
        if self.path != '/api/chat':
            self.reply(404, {'error':'ROUTE_NOT_FOUND'}); return
        ident, model, messages = data.get('id'), data.get('model'), data.get('messages')
        if not isinstance(ident,str) or not 8 <= len(ident) <= 80 or not isinstance(model,str) or len(model)>160 or not isinstance(messages,list) or not 1<=len(messages)<=21:
            self.reply(400, {'error':'CHAT_INPUT'}); return
        if any(not isinstance(m,dict) or m.get('role') not in ('user','assistant') or not isinstance(m.get('content'),str) or len(m['content'])>8000 for m in messages) or messages[-1]['role']!='user':
            self.reply(400, {'error':'CHAT_CONTENT'}); return
        try:
            if model not in models():
                self.reply(409, {'error':'MODEL_NOT_INSTALLED'}); return
            body = json.dumps({'model':model,'messages':messages,'stream':True}, ensure_ascii=False).encode('utf-8')
            req = ur.Request('http://127.0.0.1:11434/api/chat',body,{'Content-Type':'application/json'},method='POST')
            upstream = opener.open(req, timeout=120)
        except Exception as e:
            self.reply(503, {'error':'OLLAMA_UNAVAILABLE', 'type':type(e).__name__}); return
        task = {'stop':threading.Event(),'upstream':upstream}
        with LOCK:
            if ident in ACTIVE:
                upstream.close(); self.reply(409, {'error':'ID_ACTIVE'}); return
            ACTIVE[ident]=task
        self.send_response(200)
        self.send_header('Content-Type','application/x-ndjson; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Connection','close')
        self.end_headers()
        try:
            with upstream:
                for raw in upstream:
                    if task['stop'].is_set(): break
                    if len(raw)>65536: raise ValueError('FRAME_TOO_LARGE')
                    frame=json.loads(raw)
                    if not isinstance(frame, dict): raise ValueError('BAD_FRAME')
                    if frame.get('error'): raise ValueError('OLLAMA_ERROR')
                    delta=frame.get('message',{}).get('content','')
                    if not isinstance(delta,str): raise ValueError('BAD_DELTA')
                    item={'delta':delta,'done':frame.get('done') is True}
                    self.wfile.write((json.dumps(item,ensure_ascii=False)+'\n').encode('utf-8'))
                    self.wfile.flush()
                    if item['done']: break
        except (OSError, BrokenPipeError, ConnectionError):
            pass
        except Exception as e:
            try:
                self.wfile.write((json.dumps({'error':type(e).__name__})+'\n').encode('utf-8'))
                self.wfile.flush()
            except OSError: pass
        finally:
            with LOCK: ACTIVE.pop(ident,None)

if __name__ == '__main__':
    print(f'NOX D02 WEB running on http://127.0.0.1:{PORT}',flush=True)
    ThreadingHTTPServer(('127.0.0.1',PORT), Web).serve_forever()

'@
  $htmlCode = @'
<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>NOX HELION · D02 · Local WEB</title>
<style>
:root{color-scheme:dark;--edge:#c69b6d;--text:#f6ebdf;--muted:#aab4c5}*{box-sizing:border-box}
body{margin:0;background:#05070d;color:var(--text);font:14px/1.5 "Segoe UI",system-ui,sans-serif}
header{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:12px clamp(14px,3vw,46px);border-bottom:1px solid #c69b6d35;background:#090e17}
h1{font-size:17px;margin:0;letter-spacing:.2em;font-weight:500}small{display:block;letter-spacing:.12em;color:var(--muted)}
.status{color:#f3c188;font-size:12px}.layout{display:grid;grid-template-columns:minmax(145px,210px) minmax(0,1fr) minmax(155px,220px);gap:14px;padding:14px;max-width:1900px;margin:auto}
aside,.chat{border:1px solid #c69b6d35;border-radius:15px;background:#0c1320df;padding:14px;min-width:0}aside h2{font-size:12px;letter-spacing:.17em;color:#edc18e;margin:4px 0 16px}
button,select,textarea{font:inherit;color:inherit;background:#111b2d;border:1px solid #aa855971;border-radius:10px}button{cursor:pointer;padding:9px 10px}button:hover{border-color:#e8be8b}button:focus-visible,select:focus-visible,textarea:focus-visible{outline:2px solid #91edff;outline-offset:2px}
.core{width:100%;text-align:left;margin:0 0 7px}.core[aria-pressed=true]{border-color:#b8eaff;background:#19334a}
.center{min-width:0}.hero{position:relative;min-height:220px;background:#050710;border:1px solid #c69b6d44;border-radius:18px;overflow:hidden}.hero img{width:100%;height:auto;max-height:58vh;object-fit:contain;display:block;margin:auto}.source{position:absolute;bottom:10px;left:10px;font-size:10px;letter-spacing:.07em;background:#04080dcc;border-radius:7px;padding:4px 7px;color:#b8c9d8}
.chat{margin-top:14px}.chat h2{font-weight:500;margin:0 0 10px;letter-spacing:.11em}.messages{height:min(30vh,280px);min-height:160px;overflow:auto;background:#050a12;border:1px solid #44515d;border-radius:12px;padding:12px;white-space:pre-wrap;overflow-wrap:anywhere}
.msg{margin:0 0 12px;padding:9px 12px;border-radius:12px;max-width:93%}.msg.user{margin-left:auto;background:#433226}.msg.assistant{margin-right:auto;background:#183847}
.controls{display:flex;flex-wrap:wrap;gap:9px;align-items:center;margin-top:10px}.controls textarea{width:100%;resize:vertical;min-height:65px;padding:11px}.controls select{padding:9px;min-width:160px;max-width:100%}.controls button{min-width:100px}.controls button:disabled{opacity:.45;cursor:not-allowed}
.notice{font-size:12px;color:var(--muted)}.facts{font-size:12px;color:#c6d9e5}.facts strong{color:#f3c188}
@media(max-width:1000px){.layout{grid-template-columns:minmax(110px,180px) minmax(0,1fr)}aside.right{grid-column:1/-1}.hero img{max-height:54vh}}
@media(max-width:640px){header{flex-wrap:wrap}.layout{display:flex;flex-direction:column}.cores{display:grid;grid-template-columns:repeat(4,1fr);gap:5px}.core{font-size:10px;padding:8px 3px;margin:0;text-align:center}.hero img{max-height:42vh}.messages{height:230px}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important;scroll-behavior:auto!important}}
</style></head><body>
<header><div><h1>NOX HELION</h1><small>ORIGINAL APPROVED D02 · LOCAL WEB</small></div><div class="status" id="state">Проверяю локальную модель…</div></header>
<div class="layout"><aside><h2>ВОСЕМЬ CORE ID</h2><nav class="cores" id="cores" aria-label="Ядра NOX"></nav><p class="notice">Каждый CoreID использует текущую локальную модель; переключение меняет контекст беседы.</p></aside>
<main class="center"><div class="hero"><img src="/assets/home-approved.png" alt="Утверждённая пользователем графика NOX HELION D02"><div class="source">ORIGINAL APPROVED HOME · без перерисовки</div></div>
<section class="chat"><h2>ЦЕНТРАЛЬНЫЙ CHAT · AUTO CORE</h2><div id="messages" class="messages" role="log" aria-live="polite"></div>
<div class="controls"><label for="model">Локальная модель</label><select id="model" aria-label="Установленная модель"></select><textarea id="prompt" placeholder="Сообщение NOX… Enter — отправить, Shift+Enter — новая строка"></textarea><button id="send">ОТПРАВИТЬ</button><button id="stop" disabled>■ STOP</button></div>
<p class="notice" id="info">Ожидание подключения к Ollama…</p></section></main>
<aside class="right"><h2>РЕАЛЬНЫЕ СОСТОЯНИЯ</h2><div class="facts" id="facts">Модель: ожидаем Ollama</div><p class="notice">S03/SQLite, GPU/VRAM и обучение здесь не имитируются. Их подключение — следующие блоки.</p></aside></div>
<script>
(()=>{
'use strict'; const $=id=>document.getElementById(id); const coreIds=['CONSCIOUSNESS','ATLAS','REFLECTION','NEXUS','FORGE','CORE','VOICE','PERSONA'];
let core='CORE',token='',model='',busy=null;const history=new Map();
function say(s){$('state').textContent=s;$('info').textContent=s;}
function drawCore(){const box=$('cores');box.replaceChildren();for(const id of coreIds){const b=document.createElement('button');b.type='button';b.className='core';b.textContent=id;b.setAttribute('aria-pressed',String(core===id));b.onclick=()=>{if(busy)return;core=id;drawCore();renderHistory();};box.append(b)}}
function chatKey(){return core+'|'+model}
function message(role,text){const p=document.createElement('p');p.className='msg '+role;p.textContent=text;$('messages').append(p);$('messages').scrollTop=$('messages').scrollHeight;return p;}
function renderHistory(){$('messages').replaceChildren();for(const m of history.get(chatKey())||[])message(m.role,m.content);$('facts').textContent='CoreID: '+core+' | Модель: '+model+' | История: только текущая вкладка';}
async function api(path,data){const res=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-NOX-Token':token},body:JSON.stringify(data)});return {res,body:res.ok?null:await res.json().catch(()=>({error:'HTTP_'+res.status}))}}
async function send(){const text=$('prompt').value.trim();if(!text||!model||!token||busy)return;const key=chatKey();const previous=history.get(key)||[];const requestId=crypto.randomUUID();const ctl=new AbortController();busy={requestId,ctl,key,stopped:false};$('send').disabled=true;$('stop').disabled=false;$('prompt').value='';message('user',text);const bubble=message('assistant','');say('STREAMING · '+model);let answer='',done=false;
try{const messages=[...previous,{role:'user',content:text}].slice(-21);const res=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json','X-NOX-Token':token},body:JSON.stringify({id:requestId,model,messages}),signal:ctl.signal});if(!res.ok||!res.body)throw Error((await res.json().catch(()=>({error:'HTTP_'+res.status}))).error);const reader=res.body.getReader();const decoder=new TextDecoder();let buffer='';while(!done){const packet=await reader.read();if(packet.done)break;buffer+=decoder.decode(packet.value,{stream:true});let n;while((n=buffer.indexOf('\n'))>=0){const line=buffer.slice(0,n).trim();buffer=buffer.slice(n+1);if(!line)continue;const data=JSON.parse(line);if(data.error)throw Error(data.error);if(typeof data.delta!=='string'||typeof data.done!=='boolean')throw Error('STREAM_INVALID');answer+=data.delta;bubble.textContent=answer;done=data.done;if(done)break;}}
if(!done||!answer.trim())throw Error('NO_VERIFIED_ANSWER');history.set(key,[...previous,{role:'user',content:text},{role:'assistant',content:answer}].slice(-20));say('COMPLETED · реальный ответ Ollama');}catch(e){if(!busy?.stopped)say('HOLD · '+String(e.message).slice(0,100));if(!answer)bubble.textContent='Генерация не завершена';}finally{busy=null;$('send').disabled=false;$('stop').disabled=true;}}
async function stop(){if(!busy)return;const current=busy;current.stopped=true;current.ctl.abort();try{await api('/api/stop',{id:current.requestId})}catch{}say('STOP REQUESTED · незавершённый ответ не сохранён');}
async function boot(){drawCore();$('send').disabled=true;try{const res=await fetch('/api/session',{cache:'no-store'});const data=await res.json();if(!res.ok||!Array.isArray(data.models)||!data.models.length)throw Error('OLLAMA_MODELS_UNAVAILABLE');token=data.token;const select=$('model');for(const name of data.models){const o=document.createElement('option');o.value=o.textContent=name;select.append(o)}model=data.models.includes('qwen3:8b')?'qwen3:8b':data.models.includes('nox-helion:latest')?'nox-helion:latest':data.models[0];select.value=model;select.onchange=()=>{if(busy){select.value=model;return;}model=select.value;renderHistory()};renderHistory();$('send').disabled=false;say('OLLAMA ONLINE · '+data.models.length+' моделей');}catch(e){say('HOLD · '+e.message)}}
$('send').onclick=()=>void send();$('stop').onclick=()=>void stop();$('prompt').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();void send()}};void boot();
})();
</script></body></html>

'@
  foreach ($file in @($serverFile,$htmlFile)) {
    if (Test-Path -LiteralPath $file) {
      $backup = Join-Path $web ((Split-Path $file -Leaf) + '.before-' + (Get-Date -Format 'yyyyMMddHHmmss') + '.bak')
      Copy-Item -LiteralPath $file -Destination $backup -ErrorAction Stop
    }
  }
  [IO.File]::WriteAllText($serverFile,$serverCode,$utf8)
  [IO.File]::WriteAllText($htmlFile,$htmlCode,$utf8)
  & $python -m py_compile $serverFile
  if ($LASTEXITCODE -ne 0) { throw 'NOX_WEB_PYTHON_SYNTAX_HOLD' }
  $chosen = $null
  foreach ($port in 18765..18774) {
    if (-not (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)) {
      $chosen = $port
      break
    }
  }
  if ($null -eq $chosen) { throw 'NOX_WEB_LOCAL_PORTS_OCCUPIED' }
  $stdout = Join-Path $logs "web-$chosen.out.log"
  $stderr = Join-Path $logs "web-$chosen.err.log"
  $argsLine = "-u `"$serverFile`" `"$web`" $chosen"
  $started = Start-Process -FilePath $python -ArgumentList $argsLine -WorkingDirectory $web -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
  $url = "http://127.0.0.1:$chosen/"
  $ready = $false
  for ($i=0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 350
    try {
      $response = Invoke-RestMethod -Uri ($url + 'api/session') -TimeoutSec 3
      if ($response.status -eq 'OLLAMA_CONNECTED' -and @($response.models).Count -gt 0) {
        $ready = $true
        break
      }
    } catch {}
  }
  if (!$ready) {
    Write-Host "NOX WEB logs: $stdout / $stderr" -ForegroundColor Yellow
    throw 'NOX_WEB_START_HOLD'
  }
  Write-Host "NOX WEB D02 ONLINE: $url" -ForegroundColor Green
  Write-Host "OLLAMA INSTALLED MODELS: $($installed.Count)" -ForegroundColor Green
  Write-Host "APPROVED D02 PNG: $approved" -ForegroundColor Cyan
  Write-Host "ALL FILES INSIDE: $web" -ForegroundColor Cyan
  Write-Host 'SQLite/S03 unchanged. No models downloaded.' -ForegroundColor Yellow
  Start-Process $url
}