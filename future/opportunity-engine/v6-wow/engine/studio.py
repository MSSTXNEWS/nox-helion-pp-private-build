"""Localhost-only standalone OIE studio UI. No cloud sync, no login, no publishing.
WARNING: separate future plugin preview, NOT an approved NOX Windows HOME/MENU/WORK replacement.
"""
from __future__ import annotations
import json,secrets
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlsplit
from .integration import run_job

from pathlib import Path
INDEX=(Path(__file__).with_name('studio_v6.html')).read_text(encoding='utf-8')

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
