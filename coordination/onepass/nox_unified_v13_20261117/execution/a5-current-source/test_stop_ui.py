from pathlib import Path
import importlib.util,json,hashlib,os
from functools import partial
from http.server import ThreadingHTTPServer
from threading import Thread
from playwright.sync_api import sync_playwright,expect
HERE=Path(__file__).parent
spec=importlib.util.spec_from_file_location('fixture',Path(os.environ.get('NOX_FIXTURE', str(HERE/'browser_fixture.py'))));f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
site=Path(os.environ.get('NOX_SITE_ROOT',str(HERE.parents[1]/'site'))).resolve();checks=[];errors=[]
fixture=f.SiteFixture();fixture.turns={'stop':f.Turn()}
with ThreadingHTTPServer(('127.0.0.1',0),partial(f.Handler,directory=site,fixture=fixture)) as server:
 Thread(target=server.serve_forever,daemon=True).start()
 try:
  with sync_playwright() as p:
   browser=p.chromium.launch(executable_path=os.environ.get('NOX_CHROMIUM_EXECUTABLE','chromium-headless-shell'),args=['--no-sandbox','--no-zygote','--single-process','--use-angle=swiftshader','--use-gl=angle','--disable-dev-shm-usage'])
   context=browser.new_context(reduced_motion='reduce');context.add_init_script('window.NOX_NATIVE_OWNER=true');page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)));page.goto(f'http://127.0.0.1:{server.server_port}'+f.WEB,wait_until='domcontentloaded');expect(page.locator('body')).to_have_attribute('data-v24-ready','true')
   page.locator('#prompt').fill('/photo shared media');page.locator('#prompt').press('Enter');expect(page.locator('.nox-media-status')).to_contain_text('В очереди')
   page.locator('#prompt').fill('stop');page.locator('#prompt').press('Enter');assert fixture.turns['stop'].received.wait(5)
   rid=[v['request_id'] for path,v in fixture.calls if path=='/api/nox/chat/stream'][0]
   page.locator('[data-action="stop"]').click();page.wait_for_function('!NOX_CHAT_V24.state().active');meta=page.locator('.v24-msg.nox .meta').last;expect(meta).to_have_text('Поток закрыт · остановка GPU не подтверждена');checks.append('Local cancellation never claims GPU stopped')
   page.evaluate("r=>dispatchEvent(new CustomEvent('nox:native-stop-receipt',{detail:r}))",{'request_id':'wrong','scoped_acknowledged':True,'gpu_stop_verified':True});expect(meta).to_have_text('Поток закрыт · остановка GPU не подтверждена');checks.append('Unrelated request receipt ignored')
   page.evaluate("r=>dispatchEvent(new CustomEvent('nox:native-stop-receipt',{detail:r}))",{'request_id':rid,'scoped_acknowledged':True,'gpu_stop_verified':False});expect(meta).to_have_text('STOP запроса принят · остановка GPU не подтверждена');checks.append('Scoped acknowledgement differs from verified GPU stop')
   page.evaluate("r=>dispatchEvent(new CustomEvent('nox:native-stop-receipt',{detail:r}))",{'request_id':rid,'scoped_acknowledged':True,'gpu_stop_verified':True});expect(meta).to_have_text('Остановка GPU подтверждена');checks.append('Verified matching receipt updates original message after transport closes')
   expect(page.locator('.nox-media-status')).to_contain_text('В очереди');assert not any('cancel' in path or 'owner/stop' in path for path,data in fixture.calls);assert not errors;checks.append('Media job unchanged; no owner STOP/task cancellation requested; zero page errors');browser.close()
 finally:
  for t in fixture.turns.values():t.release()
  server.shutdown()
receipt={'schema':'NOX_STOP_UI_SOURCE_ACCEPTANCE_V1','task_id':'1A04','scope':'real Chromium with local HTTP fixture and synthetic receipt events','native_accepted':False,'checks':checks,'passed':len(checks),'page_errors':errors,'sha256':hashlib.sha256((site/'pc/v24/nox-v24-chat.js').read_bytes()).hexdigest()};(HERE/'stop-ui-acceptance.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2));print(json.dumps(receipt,ensure_ascii=False))
