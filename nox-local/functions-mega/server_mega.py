"""Local-only, extend existing NOX read endpoints; do not replace its Ollama chat backend."""
from pathlib import Path
from urllib.parse import urlsplit
import json, sys, time, mimetypes, threading, uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/"PUSH_PACKAGES"))
from urllib import request as netreq
import server as base
import nox_services as svc
import nox_push
PORT=18773
ACTIVE={}
ACTIVE_LOCK=threading.Lock()
base.PORT=PORT
class Handler(base.Handler):
    def end_headers(self):
        self.send_header('Service-Worker-Allowed','/')
        super().end_headers()
    def do_GET(self):
        route=urlsplit(self.path).path
        if route=='/api/pc-metrics':return self._json(200,svc.truth_metrics())
        if route=='/api/training/status':return self._json(200,svc.training_status())
        if route=='/api/s03/status':return self._json(200,svc.s03_status())
        if route=='/api/push/status':
            p=svc.push_status();p['public_key']=svc.load_config().get('vapid_public_key') if p['webpush_server']=='READY' else None
            return self._json(200,p)
        if route=='/api/mega/health':return self._json(200,{'status':'READY','scope':'read-only adapters','time':int(time.time())})
        return super().do_GET()
    def do_POST(self):
        route=urlsplit(self.path).path
        origin=self.headers.get('Origin','')
        if origin not in ('',f'http://127.0.0.1:{PORT}',f'http://localhost:{PORT}'):
            return self._json(403,{'error':'origin denied'})
        if route=='/api/chat/stop':
            try:
                n=int(self.headers.get('Content-Length','0'))
                if n<2 or n>1000:return self._json(400,{'error':'invalid stop request'})
                rid=json.loads(self.rfile.read(n)).get('request_id','')
                if not isinstance(rid,str) or len(rid)>80:return self._json(400,{'error':'invalid id'})
                with ACTIVE_LOCK:
                    item=ACTIVE.get(rid)
                    if item:
                        item['stop'].set()
                        upstream=item.get('upstream')
                    else:upstream=None
                if upstream:
                    try:upstream.close()
                    except Exception:pass
                return self._json(200,{'stopped':bool(item)})
            except (ValueError,TypeError):return self._json(400,{'error':'invalid stop JSON'})
        if route=='/api/chat':return self._chat_stream()
        if route=='/api/push/subscribe':
            origin=self.headers.get('Origin','')
            if origin not in ('',f'http://127.0.0.1:{PORT}',f'http://localhost:{PORT}'):return self._json(403,{'error':'origin denied'})
            if svc.push_status()['webpush_server']!='READY':return self._json(409,{'status':'HOLD','reason':'VAPID delivery not configured'})
            try:
                n=int(self.headers.get('Content-Length','0'))
                if n<1 or n>5000:return self._json(400,{'error':'invalid subscription length'})
                data=json.loads(self.rfile.read(n))
                if not nox_push.add(data):return self._json(400,{'error':'invalid push endpoint'})
                return self._json(200,{'status':'SUBSCRIBED'})
            except (ValueError,TypeError):return self._json(400,{'error':'invalid subscription'})
        if route=='/api/push/test':
            origin=self.headers.get('Origin','')
            if origin not in ('',f'http://127.0.0.1:{PORT}',f'http://localhost:{PORT}'):return self._json(403,{'error':'origin denied'})
            return self._json(200,nox_push.send('NOX HELION','Тестовое системное уведомление'))
        if route.startswith('/api/training/') or route.startswith('/api/s03/') or route.startswith('/api/push/'):
            return self._json(409,{'status':'HOLD','reason':'Unverified trainer/S03 schema or push delivery credentials. No writes performed.'})
        return super().do_POST()
    def _chat_stream(self):
        try:
            n=int(self.headers.get('Content-Length','0'))
            if n<2 or n>65000:return self._json(400,{'error':'invalid message length'})
            data=json.loads(self.rfile.read(n)); rid=data.get('request_id')
            if not isinstance(rid,str) or len(rid)<8 or len(rid)>80:return self._json(400,{'error':'request_id required'})
            mod=data.get('model');msgs=data.get('messages')
            if mod not in {m.get('name') for m in base.models()}:return self._json(400,{'error':'model unavailable'})
            if not isinstance(msgs,list) or not 0<len(msgs)<=60:return self._json(400,{'error':'invalid history'})
            if any(not isinstance(m,dict) or m.get('role') not in ('system','user','assistant') or not isinstance(m.get('content'),str) or len(m['content'])>10000 for m in msgs):return self._json(400,{'error':'invalid message'})
            with ACTIVE_LOCK:
                if rid in ACTIVE:return self._json(409,{'error':'duplicate request id'})
                item={'stop':threading.Event(),'upstream':None}
                ACTIVE[rid]=item
            try:
                payload=json.dumps({'model':mod,'messages':msgs,'stream':True},ensure_ascii=False).encode('utf-8')
                request=netreq.Request(base.OLLAMA+'/api/chat',data=payload,headers={'Content-Type':'application/json'},method='POST')
                with netreq.urlopen(request,timeout=120) as up:
                    with ACTIVE_LOCK:item['upstream']=up
                    self.send_response(200);self.send_header('Content-Type','application/x-ndjson; charset=utf-8');self.send_header('Cache-Control','no-store');self.end_headers()
                    while not item['stop'].is_set():
                        line=up.readline()
                        if not line:break
                        self.wfile.write(line);self.wfile.flush()
            finally:
                with ACTIVE_LOCK:ACTIVE.pop(rid,None)
        except (BrokenPipeError,ConnectionResetError,ValueError,OSError) as e:
            try:
                if not self.wfile.closed:self._json(502,{'error':'local chat upstream failed or stopped'})
            except (BrokenPipeError,ConnectionResetError):pass
if __name__=='__main__':
    from http.server import ThreadingHTTPServer
    print('NOX local functional bridge: 127.0.0.1:18773',flush=True)
    nox_push.TrainerLogWatcher().start()
    ThreadingHTTPServer(('127.0.0.1',PORT),Handler).serve_forever(poll_interval=.25)