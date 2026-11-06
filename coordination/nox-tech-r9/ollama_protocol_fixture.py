"""Isolated Windows CI HTTP stream fixture: NOT a model or real Qwen."""
import json,time,sys
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
MODEL="nox-qwen-clean:latest"
class Handler(BaseHTTPRequestHandler):
 protocol_version="HTTP/1.1"
 def log_message(self,*a): pass
 def reply(self,obj,status=200):
  b=json.dumps(obj,ensure_ascii=False).encode()
  self.send_response(status);self.send_header("Content-Type","application/json; charset=utf-8")
  self.send_header("Content-Length",str(len(b)));self.end_headers();self.wfile.write(b)
 def do_GET(self):
  if self.path=="/api/tags": self.reply({"models":[{"name":MODEL}]})
  else: self.reply({"error":"fixture only"},404)
 def do_POST(self):
  if self.path!="/api/generate": self.reply({"error":"fixture only"},404);return
  try:
   length=int(self.headers.get("Content-Length","0"))
   if not 0<length<=131072: self.reply({"error":"body length"},400);return
   req=json.loads(self.rfile.read(length))
   if req.get("model")!=MODEL or req.get("stream") is not True: self.reply({"error":"model/stream"},400);return
   prompt=req.get("prompt","")
   if not isinstance(prompt,str): self.reply({"error":"prompt"},400);return
   normal="NOX_SMOKE_" in prompt
   stop="NOX_STOP_" in prompt
   if not (normal or stop): self.reply({"error":"fixture scope"},400);return
   self.send_response(200);self.send_header("Content-Type","application/x-ndjson")
   self.send_header("Transfer-Encoding","chunked");self.end_headers()
   def token(obj):
    b=(json.dumps(obj,ensure_ascii=False)+"\n").encode()
    self.wfile.write(("%x\r\n"%len(b)).encode()+b+b"\r\n");self.wfile.flush()
   if normal:
    token({"response":"4","done":False})
    token({"response":"","done":True,"eval_count":1,"eval_duration":100000000,"prompt_eval_count":18})
    self.wfile.write(b"0\r\n\r\n");self.wfile.flush();return
   for i in range(300):
    token({"response":"строка "+str(i)+" ","done":False})
    time.sleep(.07)
   token({"response":"","done":True,"eval_count":300,"eval_duration":20000000000,"prompt_eval_count":18})
   self.wfile.write(b"0\r\n\r\n");self.wfile.flush()
  except (BrokenPipeError,ConnectionResetError): pass
  except Exception as e: print("FIXTURE_ERROR",repr(e),file=sys.stderr,flush=True)
if __name__=="__main__":
 srv=ThreadingHTTPServer(("127.0.0.1",11436),Handler)
 print("FIXTURE_READY",flush=True)
 try: srv.serve_forever(.1)
 finally: srv.server_close()
