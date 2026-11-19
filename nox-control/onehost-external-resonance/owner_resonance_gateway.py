"""Private-by-login HTTPS entry to the existing native Resonance NDJSON contract."""

from hashlib import sha256
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
from pathlib import Path
import re
import threading
from urllib.parse import parse_qs, urlencode, urlsplit


LISTEN = ('127.0.0.1', 18777)
PROXY = ('127.0.0.1', 8080)
SOURCE_SHA = sha256(Path(__file__).read_bytes()).hexdigest()
PUBLIC_HOST = re.compile(r'[a-z0-9][a-z0-9-]{1,61}[a-z0-9]\.trycloudflare\.com')
ID = re.compile(r'[0-9a-f]{32}')
COOKIE = re.compile(r'(?:^|;\s*)nox_chat=([A-Za-z0-9_.=-]{1,450})\s*(?:;|$)')
GET = {'/chat/session', '/api/ui/memory/dialogs', '/api/ui/memory/dialogs/history'}
POST = {'/chat/login', '/chat/logout', '/api/ui/memory/dialogs/create', '/api/nox/chat/stream', '/api/nox/stop'}
PAGE = r'''<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>NOX HELION · Резонанс</title>
<style>
:root{color-scheme:dark;font:16px system-ui,sans-serif;background:#101114;color:#f3f1ee}*{box-sizing:border-box}body{margin:0}main{max-width:760px;margin:auto;padding:28px 18px}h1{font-size:clamp(25px,5vw,40px);margin:0 0 18px;font-weight:650}button,input,textarea,select{font:inherit;color:inherit;border:1px solid #35353d;background:#1b1c21;border-radius:11px;padding:11px}button{cursor:pointer}button:disabled{opacity:.45;cursor:default}button.primary{background:#dd9b66;border-color:#dd9b66;color:#16100b;font-weight:700}form,.row{display:flex;gap:8px;align-items:center}input,textarea,select{min-width:0;flex:1}textarea{min-height:70px;resize:vertical}#history{display:grid;gap:12px;min-height:100px;margin:18px 0}article{max-width:92%;white-space:pre-wrap;overflow-wrap:anywhere;padding:13px 15px;border-radius:12px;background:#1b1c21}article.user{justify-self:end;background:#30251d}article small{display:block;color:#b7aea6;margin-bottom:5px}#status{min-height:25px;color:#d9ac84;margin:12px 0}[hidden]{display:none!important}@media(max-width:520px){main{padding:18px 12px}.row{flex-wrap:wrap}.row select{flex-basis:100%}}
</style><main><h1>NOX HELION <span style="color:#dd9b66">· Резонанс</span></h1>
<form id="signin" hidden><input id="password" type="password" autocomplete="current-password" aria-label="Пароль NOX" placeholder="Пароль NOX" required><button class="primary">Войти</button></form>
<section id="workspace" hidden><div class="row"><select id="dialogs" aria-label="Диалог"></select><button id="new">Новый диалог</button><button id="logout">Выйти</button></div><div id="history" role="log"></div>
<form id="send"><textarea id="question" aria-label="Сообщение" placeholder="Сообщение NOX" required maxlength="8000"></textarea><button class="primary" id="submit">Отправить</button><button type="button" id="stop" disabled>Стоп</button></form></section>
<div id="status" role="status" aria-live="polite">Подключение…</div></main>
<script>
const by=id=>document.getElementById(id), banner=by('status'), list=by('dialogs'), history=by('history');
const status=text=>{banner.textContent=text;};
async function call(path,data){const response=await fetch(path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});if(!response.ok)throw new Error(String(response.status));return response;}
function bubble(role,text){const item=document.createElement('article'),label=document.createElement('small'),body=document.createElement('div');item.className=role==='user'?'user':'assistant';label.textContent=role==='user'?'Вы':'NOX';body.textContent=text;item.append(label,body);history.append(item);item.scrollIntoView({block:'nearest'});return body;}
async function showHistory(){history.replaceChildren();if(!list.value)return;const data=await (await call('/api/ui/memory/dialogs/history?dialog_id='+encodeURIComponent(list.value)+'&limit=30')).json();for(const row of data.messages||[])bubble(row.role,row.content);}
async function refresh(selected){const data=await (await call('/api/ui/memory/dialogs')).json();list.replaceChildren();for(const item of data.dialogs||[]){const option=document.createElement('option');option.value=item.dialog_id;option.textContent=item.title;list.append(option);}if(selected&&[...list.options].some(x=>x.value===selected))list.value=selected;await showHistory();}
async function open(){await refresh();by('signin').hidden=true;by('workspace').hidden=false;status('');by('question').focus();}
async function create(){const data=await (await call('/api/ui/memory/dialogs/create',{title:'Резонанс',confirmed:true})).json();await refresh(data.dialog_id);return data.dialog_id;}
by('signin').onsubmit=async event=>{event.preventDefault();const input=by('password'),password=input.value;input.value='';try{await call('/chat/login',{password});await open();}catch(error){status(error.message==='429'?'Слишком много попыток. Подождите.':'Проверьте пароль и повторите вход.');}};
by('logout').onclick=async()=>{try{await call('/chat/logout',{});}finally{location.reload();}};
by('new').onclick=async()=>{try{await create();status('');}catch{status('Диалог не создан.');}};
list.onchange=()=>showHistory().catch(()=>status('Не удалось открыть диалог.'));
by('stop').onclick=()=>call('/api/nox/stop',{}).then(()=>status('Остановка…')).catch(()=>status('Не удалось остановить ответ.'));
by('send').onsubmit=async event=>{event.preventDefault();const input=by('question'),message=input.value.trim(),submit=by('submit'),stop=by('stop');if(!message||submit.disabled)return;submit.disabled=true;stop.disabled=false;list.disabled=true;by('new').disabled=true;let saved=false;try{const dialog=list.value||await create();input.value='';bubble('user',message);const answer=bubble('assistant','');status('NOX отвечает…');const response=await call('/api/nox/chat/stream',{message,dialog_id:dialog});const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';const frame=line=>{if(!line.trim())return;const value=JSON.parse(line);if(value.type==='delta')answer.textContent+=value.text||'';if(value.type==='done')saved=value.saved===true;if(value.type==='error')throw new Error(value.error==='STREAM_STOP_REQUESTED'?'stop':'stream');};try{while(true){const part=await reader.read();if(part.done)break;buffer+=decoder.decode(part.value,{stream:true});const lines=buffer.split('\n');buffer=lines.pop();for(const line of lines)frame(line);}frame(buffer+decoder.decode());}finally{await reader.cancel().catch(()=>{});reader.releaseLock();}status(saved?'Сохранено в памяти NOX.':'Сохранение ответа не подтверждено.');}catch(error){status(error.message==='stop'?'Ответ остановлен.':'Ответ прервался. Можно повторить.');}finally{submit.disabled=false;stop.disabled=true;list.disabled=false;by('new').disabled=false;input.focus();}};
call('/chat/session').then(open).catch(()=>{by('signin').hidden=false;status('');by('password').focus();});
</script></html>'''.encode()


class Server(ThreadingHTTPServer):
    daemon_threads = True
    slots = threading.BoundedSemaphore(12)

    def get_request(self):
        stream, address = super().get_request()
        stream.settimeout(8)
        return stream, address

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        pass


class Gateway(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'NOX'
    sys_version = ''

    def log_message(self, *_):
        pass

    def headers_no_cache(self):
        self.send_header('Cache-Control', 'no-store, no-transform')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Connection', 'close')
        self.close_connection = True

    def reply(self, status, body=b'', content_type='application/json'):
        self.send_response(status)
        self.headers_no_cache()
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        if body and self.command != 'HEAD':
            self.wfile.write(body)

    def do_GET(self):
        self.route()

    def do_POST(self):
        self.route()

    def route(self):
        host = self.headers.get('Host', '').lower()
        target = urlsplit(self.path)
        if target.scheme or target.netloc or target.fragment or len(self.path) > 400:
            self.reply(400)
            return
        if self.command == 'GET' and target.path in ('/', '/chat') and not target.query:
            self.reply(200, PAGE, 'text/html; charset=utf-8')
            return
        if self.command == 'GET' and target.path == '/health' and not target.query:
            self.reply(200, b'{"ok":true,"service":"nox-resonance-gateway"}')
            return
        if self.command == 'GET' and target.path == '/_nox_edge_health' and not target.query:
            self.reply(200, json.dumps({'service': 'nox-quick-chat-gateway', 'ready': True,
                                      'source_sha256': SOURCE_SHA}, separators=(',', ':')).encode())
            return
        if self.command == 'POST' and (not PUBLIC_HOST.fullmatch(host) or self.headers.get('Origin') != 'https://' + host):
            self.reply(403)
            return
        allowed = GET if self.command == 'GET' else POST
        if target.path not in allowed:
            self.reply(404)
            return
        url = target.path
        if target.path.endswith('/history'):
            try:
                fields = parse_qs(target.query, max_num_fields=3)
            except ValueError:
                self.reply(400)
                return
            dialog = fields.get('dialog_id', [''])
            if len(dialog) != 1 or not ID.fullmatch(dialog[0]) or set(fields) - {'dialog_id', 'limit'}:
                self.reply(400)
                return
            url += '?' + urlencode({'dialog_id': dialog[0], 'limit': 30})
        elif target.query:
            self.reply(400)
            return
        body = None
        if self.command == 'POST':
            length = self.headers.get('Content-Length', '')
            if (self.headers.get('Transfer-Encoding') or self.headers.get_content_type() != 'application/json'
                    or not length.isdecimal() or not 1 <= int(length) <= 40000):
                self.reply(400)
                return
            body = self.rfile.read(int(length))
        self.forward(url, body)

    def forward(self, target, body):
        try:
            address = str(ipaddress.ip_address(self.headers.get('CF-Connecting-IP', '')))
        except ValueError:
            address = '198.51.100.7'
        headers = {'Connection': 'close', 'Accept-Encoding': 'identity', 'X-Forwarded-For': address,
                   'X-Forwarded-Proto': 'https', 'Accept': 'application/json, application/x-ndjson'}
        cookie = COOKIE.search(self.headers.get('Cookie', ''))
        if cookie:
            headers['Cookie'] = 'nox_chat=' + cookie[1]
        if body is not None:
            headers['Content-Type'] = 'application/json'
        upstream = http.client.HTTPConnection(*PROXY, timeout=180)
        try:
            upstream.request(self.command, target, body=body, headers=headers)
            result = upstream.getresponse()
            streaming = target == '/api/nox/chat/stream' and result.status == 200
            if streaming and result.getheader('Content-Type', '').split(';')[0] != 'application/x-ndjson':
                self.reply(502)
                return
            data = None if streaming else result.read(2_000_001)
            if data is not None and len(data) > 2_000_000:
                self.reply(502)
                return
        except (OSError, http.client.HTTPException):
            upstream.close()
            self.reply(502)
            return
        try:
            self.send_response(result.status)
            self.headers_no_cache()
            self.send_header('Content-Type', 'application/x-ndjson' if streaming else 'application/json')
            if target in ('/chat/login', '/chat/logout'):
                for name, value in result.getheaders():
                    if name.casefold() == 'set-cookie' and value.startswith('nox_chat=') and '\r' not in value and '\n' not in value:
                        self.send_header('Set-Cookie', value if '; secure' in value.casefold() else value + '; Secure')
            if streaming:
                self.send_header('Transfer-Encoding', 'chunked')
            else:
                self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.connection.settimeout(180)
            if streaming:
                while segment := result.read1(16384):
                    self.wfile.write(f'{len(segment):x}\r\n'.encode() + segment + b'\r\n')
                    self.wfile.flush()
                self.wfile.write(b'0\r\n\r\n')
            else:
                self.wfile.write(data)
        except (OSError, http.client.HTTPException):
            pass
        finally:
            upstream.close()


if __name__ == '__main__':
    with Server(LISTEN, Gateway) as server:
        server.serve_forever()
