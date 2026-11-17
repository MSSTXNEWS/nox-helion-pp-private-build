from pathlib import Path
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from functools import partial
from threading import Thread
from urllib.parse import unquote
import json,subprocess,re,hashlib,os
from playwright.sync_api import sync_playwright,expect
R=Path(__file__).parent;S=Path(os.environ.get('NOX_SITE_ROOT',R.parents[1]/'site'));report={'schema':'NOX_SERVICES_SOURCE_ACCEPTANCE_V1','scope':'real local Chromium; mini queue API is a local contract fixture, not OneHost','native_accepted':False,'checks':[],'widths':{},'themes':{},'page_errors':[]};tasks={};posts=[];cap={'online':True}
class Handler(SimpleHTTPRequestHandler):
 def log_message(self,*args):pass
 def reply(self,obj,status=200):
  data=json.dumps(obj).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers()
  try:self.wfile.write(data)
  except BrokenPipeError:pass
 def do_GET(self):
  path=self.path.split('?')[0]
  if path=='/api/ui/mini/capabilities':return self.reply({'schema':'NOX_MINI_CAPABILITIES_V1','commands_supported':cap['online'],'free_text':'draft','status_by_request':True})
  if path.startswith('/api/ui/mini/tasks/by-request/'):
   row=tasks.get(unquote(path.rsplit('/',1)[1]));return self.reply(row if row else {'error':'NOT_FOUND'},200 if row else 404)
  if path.startswith('/api/'):return self.reply({'status':'HOLD','error':'LOCAL_SOURCE_TEST_ONLY'},503)
  if self.path.startswith('/nox-web-v29/'):self.path=self.path[len('/nox-web-v29'):]
  return super().do_GET()
 def do_POST(self):
  if self.path!='/api/ui/mini/tasks':return self.reply({'error':'UNEXPECTED_POST'},404)
  row=json.loads(self.rfile.read(int(self.headers['Content-Length'])));posts.append(row);rid=row['request_id'];tasks[rid]={'request_id':rid,'task_id':'fixture-'+rid,'state':'AWAITING_PLAN','execution_started':False}
  if 'lost receipt' in row['text']:self.close_connection=True;return
  return self.reply(tasks[rid],202)
def okay(name):report['checks'].append(name)

with ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(S))) as server:
 Thread(target=server.serve_forever,daemon=True).start()
 with sync_playwright() as p:
  browser=p.chromium.launch(executable_path=os.environ.get('NOX_CHROMIUM_EXECUTABLE','chromium-headless-shell'),args=['--no-sandbox','--no-zygote','--single-process','--use-angle=swiftshader','--use-gl=angle','--disable-dev-shm-usage'])
  page=browser.new_page(reduced_motion='reduce');page.add_init_script("localStorage.setItem('nox_v24_rail','1')");page.goto(f'http://127.0.0.1:{server.server_port}/nox-web-v29/pc/resonance.html');page.locator('#noxCornerWorkspace').wait_for()
  page.locator('[data-action="stop"]').evaluate('(e)=>e.disabled=false')
  for w in [320,390,800,1440,3840]:
   page.set_viewport_size({'width':w,'height':max(580,min(2160,int(w*.5625)))});page.wait_for_timeout(100)
   result=page.locator('[data-action="stop"]').evaluate('(e)=>{const r=e.getBoundingClientRect();const hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return {rect:{x:r.x,y:r.y,right:r.right,bottom:r.bottom},hit:hit?.outerHTML.slice(0,180),uncovered:hit===e||e.contains(hit)}}');assert result['uncovered'],(w,result);assert result['rect']['y']>=0;print(w,result)

  browser.close()
 server.shutdown()
