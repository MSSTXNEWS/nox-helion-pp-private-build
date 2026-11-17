from pathlib import Path
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from functools import partial
from threading import Thread
import json,os
from playwright.sync_api import sync_playwright,expect
R=Path(__file__).parent;S=Path(os.environ.get('NOX_SITE_ROOT',str(R.parents[1]/'site'))).resolve();status={'code':503,'body':{'error':'OFFLINE_SOURCE_FIXTURE'}}
class Handler(SimpleHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  if self.path.startswith('/api/'):
   hit=self.path.split('?')[0]=='/api/nox/status';data=json.dumps(status['body'] if hit else {'error':'LOCAL_SOURCE_FIXTURE_ONLY'}).encode();self.send_response(status['code'] if hit else 503);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
  if self.path.startswith('/nox-web-v29/'):self.path=self.path[len('/nox-web-v29'):]
  return super().do_GET()
checks=[];errors=[];report={'scope':'actual local Chromium/WebGL assets; API fixture only','native_accepted':False,'checks':checks,'page_errors':errors,'combinations':0}
with ThreadingHTTPServer(('127.0.0.1',0),partial(Handler,directory=str(S))) as server:
 Thread(target=server.serve_forever,daemon=True).start()
 with sync_playwright() as p:
  b=p.chromium.launch(executable_path=os.environ.get('NOX_CHROMIUM_EXECUTABLE','chromium-headless-shell'),args=['--no-sandbox','--no-zygote','--single-process','--use-angle=swiftshader','--use-gl=angle','--disable-dev-shm-usage']);context=b.new_context(reduced_motion='reduce');page=context.new_page();page.set_default_timeout(15000);page.on('pageerror',lambda e:errors.append(str(e)));base=f'http://127.0.0.1:{server.server_port}/nox-web-v29/'
  page.goto(base+'studio.html',wait_until='domcontentloaded');page.wait_for_function('window.NOX_CINEMATIC_WORLDS&&window.NOX_CONNECTION_V13');expect(page.locator('.nox-connection-v13')).to_have_attribute('data-nox-connection','hold');checks.append('Offline API shows no connection; no service availability claim')
  for code,body,wanted in [(401,{'error':'AUTH'},'auth'),(200,{'model':'FIXTURE'},'partial'),(200,{'ready':True},'ok'),(200,{},'hold')]:
   status.update(code=code,body=body);page.evaluate('NOX_CONNECTION_V13.refresh()');expect(page.locator('.nox-connection-v13')).to_have_attribute('data-nox-connection',wanted)
  checks.append('Auth, non-ready JSON, explicit API-ready and empty status distinguished')
  page.evaluate("window.__material=[];addEventListener('nox-settings',e=>__material.push(e.detail))")
  palette={'gold':'amber','copper':'ember','glacier':'arctic','ion':'arctic','amethyst':'void-purple','platinum':'graphite'};shapes={}
  for world in ['helion','chronos','somnium','forge','synapse']:
   page.evaluate('(w)=>NOX_CINEMATIC_WORLDS.setWorld(w)',world)
   for color,theme in palette.items():
    page.evaluate('(c)=>NOX_CINEMATIC_WORLDS.setPalette(c)',color);assert page.evaluate('__material.at(-1).theme')==theme
    for width in [320,390,800,1440,1920,3840]:
     page.set_viewport_size({'width':width,'height':max(580,min(2160,int(width*.5625)))});page.wait_for_function('w=>innerWidth===w',arg=width);result=page.evaluate("({overflow:Math.max(0,document.documentElement.scrollWidth-innerWidth),headers:document.querySelectorAll('#noxSharedHeaderV10').length,chip:document.querySelectorAll('.nox-connection-v13').length,shape:getComputedStyle(document.body).getPropertyValue('--nox-ui-shape')})");assert result['overflow']<=1,(world,color,width,result);assert result['headers']==result['chip']==1;shapes[world]=result['shape'];report['combinations']+=1
  assert len(set(shapes.values()))==5;report['shapes']=shapes;checks.append('180 rendered theme/palette/viewport combinations; unique five materials; one header/status; no horizontal overflow')
  page.set_viewport_size({'width':1280,'height':800});page.evaluate("document.documentElement.dataset.noxDemoMode='MAX';dispatchEvent(new CustomEvent('nox-settings',{detail:{mode:'MAX'}}))")
  page.wait_for_function("window.noxContextSceneDiagnostics&&noxContextSceneDiagnostics().state==='READY'");diag=page.evaluate('noxContextSceneDiagnostics()');assert diag['canvasCount']==1;assert diag['budget']=='BALANCED',diag;assert diag['industrial']['palette']['theme']=='graphite',diag;report['context_scene']={k:diag[k] for k in ['state','canvasCount','budget','runtimeKnown','reducedMotion']};checks.append('Original inner-page Three renderer receives palette; unknown runtime clamps MAX to BALANCED')
  page.evaluate("dispatchEvent(new CustomEvent('nox-settings',{detail:null}))");checks.append('Legacy null settings event is safe')
  page.goto(base+'index.html',wait_until='domcontentloaded');page.wait_for_function('window.NOX_ORBIT_14_DEMO');home=page.evaluate('NOX_ORBIT_14_DEMO.diagnostics()');assert home['count']==14,home;report['home_objects']={k:home[k] for k in ['count','colors','giants','asteroids']};checks.append('Original HOME still has fourteen actual orbit controls')
  assert not errors,errors;page.screenshot(path=str(R/'v13-current-qa.png'));b.close()
 server.shutdown()
report['status']='SOURCE_BROWSER_PASS';(R/'browser-acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False))
