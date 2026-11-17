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
  context=browser.new_context(reduced_motion='reduce',accept_downloads=True);page=context.new_page();page.set_default_timeout(10000);page.on('pageerror',lambda e:report['page_errors'].append(str(e)));base=f'http://127.0.0.1:{server.server_port}/nox-web-v29/'
  def go(route):page.goto(base+route,wait_until='domcontentloaded');page.locator('#noxCornerWorkspace').wait_for()
  def openmini():
   if not page.locator('#cornerPanel').is_visible():page.locator('button.launch').click()
  for route in ['tools.html','world.html','calendar.html','pc/resonance.html','pc/pages/image/index.html']:
   page.set_viewport_size({'width':1280,'height':800});go(route);openmini();measure={}
   for w in [320,390,800,1440,3840]:
    page.set_viewport_size({'width':w,'height':max(580,min(2160,int(w*.5625)))});page.wait_for_function('(w)=>{const e=document.querySelector("#noxCornerWorkspace").shadowRoot.querySelector("#cornerPanel");const r=e.getBoundingClientRect();return r.x>=-1&&r.right<=w+1&&r.y>=-1&&r.bottom<=innerHeight+1}',arg=w);rect=page.locator('#cornerPanel').bounding_box();(measure.update({str(w):page.evaluate('Math.max(0,document.documentElement.scrollWidth-innerWidth)')}));assert measure[str(w)]<=1
   report['widths'][route]=measure
  okay('dock and panel visible without document overflow across 5 pages × 5 widths')
  page.locator('#cornerCommand').focus();page.keyboard.press('Escape');expect(page.locator('#cornerPanel')).to_be_hidden();page.keyboard.press('Alt+Shift+N');expect(page.locator('#cornerPanel')).to_be_visible();page.locator('button.close').click();okay('keyboard shortcut, Escape and close work')
  page.evaluate("()=>{let f=document.createElement('iframe');f.id='miniGuardFrame';f.srcdoc='<script src=\"/nox-web-v29/nox-corner-workspace.js\"><'+ '/script>';document.body.append(f)}");page.wait_for_timeout(100);assert page.frame_locator('#miniGuardFrame').locator('#noxCornerWorkspace').count()==0;okay('iframe guard prevents duplicate global workspaces')
  # Calendar CRUD, timezone and ICS use only local data.
  go('calendar.html');page.on('dialog',lambda dialog:dialog.accept());page.locator('#add-event').click();page.locator('#event-title').fill('Проверка NOX');page.locator('#event-start').fill('2026-11-17T09:00');page.locator('#event-end').fill('2026-11-17T10:00');page.locator('#event-form button[type=submit]').click();events=page.evaluate("JSON.parse(localStorage.getItem('nox.calendar.events.v1'))");assert len(events)==1;before=events[0]['start'];page.reload(wait_until='domcontentloaded');expect(page.locator('#event-count')).to_contain_text('1 событий');page.locator('.fc-event').first.click();page.locator('#event-title').fill('Исправленное событие');page.locator('#event-form button[type=submit]').click();page.locator('#timezone').fill('Europe/Madrid');page.locator('#apply-zone').click();assert page.evaluate("JSON.parse(localStorage.getItem('nox.calendar.events.v1'))[0].start")==before
  page.locator('.fc-timeGridWeek-button').click();page.locator('.fc-listMonth-button').click()
  with page.expect_download() as info:page.locator('#export-ics').click()
  saved=R/'calendar-test.ics';info.value.save_as(saved);assert 'BEGIN:VEVENT' in saved.read_text();page.locator('#import-ics').set_input_files(saved);expect(page.locator('#calendar-status')).to_contain_text('дубликатов: 1');page.locator('.fc-event').first.click();page.locator('#delete-event').click();assert page.evaluate("JSON.parse(localStorage.getItem('nox.calendar.events.v1')).length")==0;okay('Calendar real FullCalendar create/edit/reload/timezone/week/list/ICS export+dedup import/delete')
  page.evaluate("()=>{for(let i=0;i<2;i++){const id=crypto.randomUUID();localStorage.setItem('nox.corner.v1.note.'+id,JSON.stringify({schema:'NOX_CORNER_WORKSPACE_V1',localId:id,text:'Integration note '+i,version:crypto.randomUUID(),updated:new Date().toISOString()}));}}");go('world.html');expect(page.locator('.world-note')).to_have_count(2);assert page.evaluate('NoxWorld.diagnostics().interact') is True;okay('World reuses both real shared notes and Interact runtime')
  page.screenshot(path=str(R/'services-pending-qa.png'),full_page=False)
  assert not report['page_errors'],report['page_errors']
  context.close();browser.close()
 server.shutdown()
report['request_count']=len(posts);report['posts']=posts;report['status']='SOURCE_BROWSER_PASS';(R/'pending-acceptance.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False,indent=2))
