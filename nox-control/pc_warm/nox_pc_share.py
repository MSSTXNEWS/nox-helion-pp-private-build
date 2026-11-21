"""NOX PC share: слушает ТОЛЬКО 127.0.0.1:8765. Сервер NOX достаёт его через обратный SSH-туннель.
GET  /<путь>        — файлы из ..\MODELS (только чтение, поддержка Range для докачки)
GET  /backups/      — список бэкапов
PUT  /backups/<имя> — сохранить бэкап в ..\BACKUPS (только туда, без подпапок, без перезаписи существующего)"""
import os, re, sys, json
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import unquote
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, '..'))
MODELS = os.path.join(ROOT, 'MODELS'); BACKUPS = os.path.join(ROOT, 'BACKUPS'); os.makedirs(BACKUPS, exist_ok=True)
NAME = re.compile(r'^[A-Za-z0-9._-]{1,120}$')
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, body=b'', ctype='application/json', extra=None):
        self.send_response(code); self.send_header('Content-Type', ctype); self.send_header('Content-Length', str(len(body)))
        for k, v in (extra or {}).items(): self.send_header(k, v)
        self.end_headers()
        if self.command != 'HEAD': self.wfile.write(body)
    def _resolve(self, p):
        p = unquote(p.split('?')[0]).lstrip('/')
        full = os.path.abspath(os.path.join(MODELS, p))
        return full if full == MODELS or full.startswith(MODELS + os.sep) else None
    def do_HEAD(self): self.do_GET()
    def do_GET(self):
        path = unquote(self.path.split('?')[0])
        if path.rstrip('/') == '/backups':
            rows = [{'name': n, 'size': os.path.getsize(os.path.join(BACKUPS, n))} for n in sorted(os.listdir(BACKUPS))]
            return self._send(200, json.dumps(rows).encode())
        full = self._resolve(path)
        if not full: return self._send(403, b'{"error":"forbidden"}')
        if os.path.isdir(full):
            rows = [{'name': n + ('/' if os.path.isdir(os.path.join(full, n)) else ''), 'size': (os.path.getsize(os.path.join(full, n)) if os.path.isfile(os.path.join(full, n)) else 0)} for n in sorted(os.listdir(full))]
            return self._send(200, json.dumps(rows).encode())
        if not os.path.isfile(full): return self._send(404, b'{"error":"not found"}')
        size = os.path.getsize(full); start, end, code = 0, size - 1, 200
        m = re.match(r'bytes=(\d*)-(\d*)', self.headers.get('Range', ''))
        if m and (m.group(1) or m.group(2)):
            if m.group(1): start = int(m.group(1)); end = int(m.group(2)) if m.group(2) else size - 1
            else: start = max(0, size - int(m.group(2)))
            if start >= size: return self._send(416, b'', extra={'Content-Range': 'bytes */%d' % size})
            end = min(end, size - 1); code = 206
        n = end - start + 1
        self.send_response(code); self.send_header('Content-Type', 'application/octet-stream'); self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(n))
        if code == 206: self.send_header('Content-Range', 'bytes %d-%d/%d' % (start, end, size))
        self.end_headers()
        if self.command == 'HEAD': return
        with open(full, 'rb') as f:
            f.seek(start); left = n
            while left > 0:
                b = f.read(min(1 << 20, left))
                if not b: break
                self.wfile.write(b); left -= len(b)
    def do_PUT(self):
        path = unquote(self.path.split('?')[0])
        m = re.match(r'^/backups/([^/]+)$', path)
        if not m or not NAME.match(m.group(1)): return self._send(403, b'{"error":"only /backups/<name> allowed"}')
        dest = os.path.join(BACKUPS, m.group(1))
        if os.path.exists(dest): return self._send(409, b'{"error":"exists"}')
        left = int(self.headers.get('Content-Length', '0')); tmp = dest + '.part'
        with open(tmp, 'wb') as f:
            while left > 0:
                b = self.rfile.read(min(1 << 20, left))
                if not b: break
                f.write(b); left -= len(b)
        if left: os.remove(tmp); return self._send(400, b'{"error":"short body"}')
        os.replace(tmp, dest); self._send(201, json.dumps({'ok': True, 'name': m.group(1), 'size': os.path.getsize(dest)}).encode())
if __name__ == '__main__':
    print('NOX share: 127.0.0.1:8765  MODELS=%s  BACKUPS=%s' % (MODELS, BACKUPS)); sys.stdout.flush()
    ThreadingHTTPServer(('127.0.0.1', 8765), H).serve_forever()
