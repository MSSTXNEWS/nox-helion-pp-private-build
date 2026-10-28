"""OPTIONAL localhost-only preview for NOX web panel.

The native Windows NOX host should call Studio.dispatch() directly via its own
origin-restricted WebView2 message bridge. This preview is never a production
remote-access gateway, and it intentionally binds ONLY 127.0.0.1.
"""
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit
from .creative_extensions import MAX_UPLOAD
from .engine import Studio, StudioError

ROOT=Path(__file__).resolve().parent.parent
WEB=ROOT/'web';ASSETS=ROOT/'assets'


def launch(port=8765, data_dir=None):
    studio=Studio(data_dir or ROOT/'runtime')
    token=secrets.token_urlsafe(30)
    content_types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8',
                   '.css':'text/css; charset=utf-8','.json':'application/json; charset=utf-8',
                   '.png':'image/png','.svg':'image/svg+xml','.webmanifest':'application/manifest+json',
                   '.mp4':'video/mp4','.webm':'video/webm','.glb':'model/gltf-binary','.wav':'audio/wav'}
    class Handler(BaseHTTPRequestHandler):
        def _send(self,status,body,mime='application/json; charset=utf-8'):
            self.send_response(status);self.send_header('Content-Type',mime)
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('X-Frame-Options','SAMEORIGIN');self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; base-uri 'none'")
            self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def _host_ok(self):
            return self.headers.get('Host','').split(':')[0] in ('127.0.0.1','localhost')
        def do_GET(self):
            if not self._host_ok():return self._send(403,b'Forbidden')
            target=urlsplit(self.path).path
            if target=='/api/bootstrap':
                return self._send(200,json.dumps({'csrf':token,'local_preview':True}).encode())
            if target.startswith('/api/media/'):
                bits=unquote(target).split('/')
                if len(bits)!=5 or not bits[3] or not bits[4]:return self._send(404,b'Not found')
                try:
                    folder=studio._project(bits[3]);media=studio._within(folder,folder/bits[4])
                    if not media.is_file() or media.suffix.lower() not in ('.mp4','.webm','.wav','.glb'):
                        return self._send(404,b'Not found')
                    payload=media.read_bytes()
                    return self._send(200,payload,content_types.get(media.suffix.lower(),'application/octet-stream'))
                except (StudioError,OSError):return self._send(404,b'Not found')
            rel=unquote(target.lstrip('/')) or 'studio.html'
            path=(ASSETS / rel.removeprefix('assets/')) if rel.startswith('assets/') else WEB/rel
            base=ASSETS if rel.startswith('assets/') else WEB
            path=path.resolve()
            if not path.is_relative_to(base.resolve()) or not path.is_file():return self._send(404,b'Not found')
            return self._send(200,path.read_bytes(),content_types.get(path.suffix,'application/octet-stream'))
        def do_POST(self):
            if not self._host_ok():return self._send(403,b'Forbidden')
            origin=self.headers.get('Origin','')
            if origin not in ('','http://127.0.0.1:'+str(port),'http://localhost:'+str(port)):
                return self._send(403,b'Forbidden')
            if self.headers.get('X-NOX-CSRF','')!=token:
                return self._send(403,b'Forbidden')
            if self.path=='/api/upload':
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=MAX_UPLOAD:raise StudioError('Upload size exceeds 256 MiB')
                    result=studio.upload(self.headers.get('X-NOX-Project',''),
                        unquote(self.headers.get('X-NOX-Filename','')),self.rfile,size)
                    return self._send(200,json.dumps({'ok':True,'data':result}).encode())
                except (ValueError,StudioError,TypeError) as exc:
                    return self._send(400,json.dumps({'ok':False,'error':str(exc)}).encode())
            if self.path!='/api/dispatch':return self._send(404,b'Not found')
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=262144:raise StudioError('Invalid payload size')
                payload=json.loads(self.rfile.read(size))
                result=studio.dispatch(payload)
                self._send(200,json.dumps({'ok':True,'data':result},ensure_ascii=False).encode())
            except (ValueError,StudioError,TypeError) as exc:
                self._send(400,json.dumps({'ok':False,'error':str(exc)},ensure_ascii=False).encode())
            except Exception as exc:
                self._send(503,json.dumps({'ok':False,'error':'Adapter error: '+type(exc).__name__}).encode())
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    print('NOX CREATIVE LOCAL PREVIEW: http://127.0.0.1:'+str(port)+'/studio.html')
    print('Remote/mobile use: deploy through your authenticated HTTPS NOX host, not this preview server.')
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()

if __name__=='__main__':launch()
