
import json,sys,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
def mk(body):
    class H(BaseHTTPRequestHandler):
        def log_message(s,*a):pass
        def do_GET(s):
            if s.path=="/health":
                d=json.dumps(body).encode();s.send_response(200);s.send_header("Content-Type","application/json");s.send_header("Content-Length",str(len(d)));s.end_headers();s.wfile.write(d)
            else:s.send_response(404);s.end_headers()
    return H
stt={"ok":True,"service":"nox-stt","ready":True,"model":{"name":"faster-whisper small"},"sessions":0}
tts={"ok":True,"service":"nox-tts","ready":False,"ready_note":"XTTS не загружен: нет модели","backends":[{"name":"piper","available":True},{"name":"xtts","available":False}],"out_rate":24000}
for p,b in ((8093,stt),(8094,tts)):
    threading.Thread(target=ThreadingHTTPServer(("127.0.0.1",p),mk(b)).serve_forever,daemon=True).start()
threading.Event().wait()
