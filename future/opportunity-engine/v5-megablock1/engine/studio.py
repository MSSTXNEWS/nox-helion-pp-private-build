"""Localhost-only standalone OIE studio UI. No cloud sync, no login, no publishing.
WARNING: separate future plugin preview, NOT an approved NOX Windows HOME/MENU/WORK replacement.
"""
from __future__ import annotations
import json,secrets
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlsplit
from .integration import run_job

INDEX='''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>NOX · Opportunity Laboratory</title><style>
:root{color-scheme:dark;font-family:Inter,Segoe UI,Arial,sans-serif;--gold:#e6ad65;--blue:#8cd8e8;--line:rgba(162,201,221,.18)}*{box-sizing:border-box}body{background:radial-gradient(ellipse at 50% 0%,#142736 0%,#080e17 45%,#05080e 100%);color:#e9f0f8;margin:0;min-height:100vh}
header{padding:24px max(24px,6vw);border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px}.brand{font-size:23px;font-weight:780;letter-spacing:.10em}.brand span{color:var(--gold)}.small{font:12px/1.6 ui-monospace,monospace;letter-spacing:.08em;color:#8ba5b8}.flag{border:1px solid #4a6678;border-radius:30px;padding:8px 12px;color:#c1d9dc;font-size:12px}
main{max-width:1350px;margin:auto;padding:26px max(24px,4vw)}h1{font-size:clamp(29px,3.5vw,53px);letter-spacing:-.045em;margin:10px 0}h1 em{font-style:normal;color:var(--gold)}.desc{max-width:770px;color:#9dafbe;line-height:1.65}
.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:26px 0}.stat,.panel,.idea{background:linear-gradient(130deg,rgba(28,47,66,.72),rgba(11,21,34,.9));border:1px solid var(--line);border-radius:15px}.stat{padding:18px}.stat b{display:block;font-size:26px;color:#dceaf6}.stat small{font-size:11px;color:#9bafc0}.panel{padding:22px;margin-bottom:20px}.panel h2{font-size:18px;margin:0 0 14px;color:var(--blue)}.controls{display:flex;gap:8px;flex-wrap:wrap}input,button{border-radius:9px;padding:12px 14px;font:inherit}input{background:#091522;color:#fff;border:1px solid #446277;min-width:0;flex:1}button{background:linear-gradient(100deg,#c78b48,#f3c782);color:#131b23;font-weight:750;border:0;cursor:pointer}button:disabled{opacity:.5;cursor:wait}.tiny{padding:10px 12px;background:#172b3f;color:#c9e6e8;border:1px solid var(--line)}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:13px}.idea{padding:16px;min-height:145px;cursor:pointer}.idea:hover{border-color:#78d7dc}.idea h3{font-size:15px;margin:9px 0}.meta{font:11px ui-monospace,monospace;color:#9ad3df}.tag{font-size:10px;display:inline-block;padding:5px 8px;border-radius:30px;color:#efcd95;background:#39291b}.muted{font-size:12px;color:#a2b5c5;line-height:1.5}.code{overflow-wrap:anywhere;white-space:pre-wrap;font:12px/1.5 ui-monospace,monospace;color:#a5d6e5}footer{text-align:center;padding:18px;color:#768ca0;font-size:12px}#result{min-height:45px}
@media(max-width:850px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.stats{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:550px){.grid{grid-template-columns:1fr}header{padding:20px}.controls{flex-direction:column}input{width:100%}}@media(prefers-reduced-motion:no-preference){.idea,.panel{transition:border-color .2s ease}}:focus-visible{outline:2px solid #ffd291;outline-offset:3px}
</style></head><body><header><div class="brand">NOX <span>HELION</span></div><div class="small">OPPORTUNITY INVENTION LAB · V4</div><div class="flag">● LOCAL · FUTURE MODULE · MB1</div></header><main><div class="small">NOX CORE / VENTURE FOUNDRY / IDEATION</div><h1>От проблемы — <em>к новой возможности.</em></h1><p class="desc">Исследовательская лаборатория идей. Пока гипотезы не проверены, они остаются гипотезами. Никаких автоплатежей, публикаций и маркетинговых утверждений.</p><section class="stats"><div class="stat"><b>60</b><small>ИСХОДНЫХ КОНЦЕПЦИЙ</small></div><div class="stat"><b>12</b><small>ПОИСКОВЫХ ЯДЕР</small></div><div class="stat"><b>0</b><small>ПОДТВЕРЖДЁННЫХ ПИЛОТОВ</small></div><div class="stat"><b>HOLD</b><small>КОММЕРЧЕСКИЙ ДОПУСК</small></div></section><section class="panel"><h2>Сгенерировать новые концепции</h2><p class="muted">Локальный генератор комбинирует подготовленные проблемные сценарии. Не обращается к интернету и не подменяет данные рынка.</p><form id="form" class="controls"><input id="theme" maxlength="240" placeholder="Тема (необязательно), например family, education, business" aria-label="Тема"><button id="generate" type="submit">Найти 3 идеи</button><button id="megablock1" type="button" class="tiny">МЕГА-БЛОК 1 · Паспорта + QA</button></form><div id="result" role="status" aria-live="polite"></div></section><section class="panel"><h2>Каталог исходных гипотез <span class="muted">60 · IDEA_UNVERIFIED</span></h2><div class="controls"><input id="filter" placeholder="Поиск по каталогу" aria-label="Поиск по каталогу"><button class="tiny" id="reset" type="button">Сбросить</button></div><div class="grid" id="catalog"></div></section><section class="panel"><h2>Инспектор</h2><pre id="inspector" class="code" aria-live="polite">Нажмите на карточку идеи, чтобы увидеть проверки и блокировки.</pre></section></main><footer>NOX HELION · OFFLINE FUTURE MODULE · OWNER-CONTROLLED RESEARCH · NOT A RELEASE 1 UI</footer><script>
const token='__TOKEN__';const esc=document.createElement('div');let all=[];const holder=document.querySelector('#catalog');
function p(tag,value,cls){let x=document.createElement(tag);x.textContent=String(value||'');if(cls)x.className=cls;return x}
function render(items){holder.replaceChildren();for(const d of items){let c=p('article','','idea');c.tabIndex=0;c.setAttribute('role','button');c.append(p('div',d.id,'meta'),p('h3',d.name),p('span',d.status,'tag'));function details(){fetch('/api/inspect?id='+encodeURIComponent(d.id)).then(x=>x.json()).then(x=>{document.querySelector('#inspector').textContent=JSON.stringify(x.result||x,null,2)}).catch(()=>{document.querySelector('#inspector').textContent='READ_ERROR'})}c.onclick=details;c.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();details()}};holder.append(c)}}
fetch('/api/ideas').then(r=>r.json()).then(j=>{all=j.result.ideas;render(all)});document.querySelector('#filter').oninput=e=>{let s=e.target.value.toLowerCase();render(all.filter(x=>(x.name+' '+x.id).toLowerCase().includes(s)))};document.querySelector('#reset').onclick=()=>{document.querySelector('#filter').value='';render(all)};
document.querySelector('#megablock1').onclick=async()=>{const button=document.querySelector('#megablock1');button.disabled=true;const el=document.querySelector('#result');el.textContent='Формирование проверяемых паспортов…';try{const response=await fetch('/api/megablock1',{method:'POST',headers:{'Content-Type':'application/json','X-NOX-OIE-Token':token},body:JSON.stringify({theme:document.querySelector('#theme').value,count:3})});const result=await response.json();if(!result.ok)throw Error(result.error||'MISSION_FAILED');el.replaceChildren();const data=result.result;for(const d of data.passports){const article=p('article','','idea');article.append(p('div',d.idea_id,'meta'),p('h3',d.name),p('p',d.problem_hypothesis,'muted'),p('p','Первые 5 минут: '+d.first_five_minutes,'muted'),p('p','Что проверять: '+d.missing_evidence.join(' · '),'muted'),p('span','IDEA_UNVERIFIED · HOLD','tag'));el.append(article)}el.append(p('p','SHA паспортов: '+data.receipts.passports_sha256+' · никаких разрешённых коммерческих действий','code'))}catch(error){el.textContent='МЕГА-БЛОК 1: '+error.message}finally{button.disabled=false}};
document.querySelector('#form').onsubmit=async e=>{e.preventDefault();let btn=document.querySelector('#generate');btn.disabled=true;try{let r=await fetch('/api/mission',{method:'POST',headers:{'Content-Type':'application/json','X-NOX-OIE-Token':token},body:JSON.stringify({theme:document.querySelector('#theme').value,count:3})});let j=await r.json();let el=document.querySelector('#result');el.replaceChildren();if(!j.ok)throw Error(j.error||'FAILED');for(const d of j.result.results){let v=p('article','','idea');v.append(p('h3',d.candidate.name),p('p',d.candidate.first_5min_value||'Гипотеза требует проверки','muted'),p('span','IDEA_UNVERIFIED · пилот не разрешён','tag'));el.append(v)}}catch(e){document.querySelector('#result').textContent='Невозможно выполнить: '+e.message}finally{btn.disabled=false}}
</script></body></html>'''

class Server(ThreadingHTTPServer):daemon_threads=True;allow_reuse_address=True

def make_handler(token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,fmt,*args):pass
        def _valid_host(self):
            host=self.headers.get('Host','').lower().split(':')[0]
            return host in {'127.0.0.1','localhost'}
        def _json(self,body,status=200):
            b=json.dumps(body,ensure_ascii=False).encode()
            self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Security-Policy',"default-src 'none'");self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
        def do_GET(self):
            if not self._valid_host():return self._json({'error':'BAD_HOST'},403)
            path=urlsplit(self.path).path
            if path=='/':
                b=INDEX.replace('__TOKEN__',token).encode()
                self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('X-Frame-Options','DENY');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'");self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
            elif path=='/api/ideas':self._json(run_job({'contract':'nox.oie.job.v1','action':'idea.list'}))
            elif path=='/api/capabilities':self._json(run_job({'contract':'nox.oie.job.v1','action':'capabilities'}))
            elif path=='/api/inspect':
                from urllib.parse import parse_qs
                ident=parse_qs(urlsplit(self.path).query).get('id',[''])[0]
                self._json(run_job({'contract':'nox.oie.job.v1','action':'idea.inspect','idea_id':ident}))
            else:self._json({'error':'NOT_FOUND'},404)
        def do_POST(self):
            if not self._valid_host():return self._json({'ok':False,'error':'BAD_HOST'},403)
            origin=self.headers.get('Origin','')
            if origin and urlsplit(origin).hostname not in {'127.0.0.1','localhost'}:return self._json({'ok':False,'error':'BAD_ORIGIN'},403)
            if self.headers.get('X-NOX-OIE-Token')!=token:return self._json({'ok':False,'error':'TOKEN_REQUIRED'},403)
            path=urlsplit(self.path).path
            if path not in {'/api/mission','/api/megablock1'}:return self._json({'error':'NOT_FOUND'},404)
            try:
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<=10000:raise ValueError('SIZE_INVALID')
                body=json.loads(self.rfile.read(n))
                res=run_job({'contract':'nox.oie.job.v1','action':'megablock1.preview' if path=='/api/megablock1' else 'mission.run',
                             'parameters':{'theme':body.get('theme',''),'count':body.get('count',3)}})
                return self._json(res,200 if res['ok'] else 400)
            except (ValueError,TypeError,KeyError,AttributeError):self._json({'ok':False,'error':'INVALID_REQUEST'},400)
    return Handler

def serve(host='127.0.0.1',port=8765):
    if host!='127.0.0.1':raise ValueError('LOCAL_BIND_ONLY')
    if not isinstance(port,int) or not 1024<=port<=65535:raise ValueError('PORT_OUT_OF_RANGE')
    token=secrets.token_urlsafe(32)
    http=Server((host,port),make_handler(token))
    print('NOX OIE V5 MB1 studio: http://127.0.0.1:'+str(http.server_port),flush=True)
    try:http.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:pass
    finally:http.server_close()
