import json
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
  b=p.chromium.launch(args=['--use-gl=swiftshader','--enable-unsafe-swiftshader'])
  for w in (390,1440):
    pg=b.new_page(viewport={'width':w,'height':844}); pend={}; log=[]
    pg.on('request',lambda r:pend.__setitem__(r.url,r.resource_type))
    pg.on('requestfinished',lambda r:pend.pop(r.url,None)); pg.on('requestfailed',lambda r:pend.pop(r.url,None))
    pg.on('pageerror',lambda e:log.append('PE '+str(e)[:150]))
    pg.on('console',lambda m:log.append(m.type+' '+m.text[:120]) if m.type in('error','warning') else None)
    pg.route('**/api/nox/outbox*',lambda r:r.fulfill(status=200,content_type='application/json',body='{"messages":[]}'))
    pg.goto('http://127.0.0.1:18091/web/chat-dc.html',wait_until='commit',timeout=30000)
    for t in (3,10,20):
      pg.wait_for_timeout(t*1000 if t==3 else 8000)
      try: rs=pg.evaluate("document.readyState")
      except Exception as e: rs='ERR'
      print(json.dumps({'w':w,'t':t,'ready':rs,'pending':[(k.split('18091')[-1][:70],v) for k,v in pend.items()][:12],'log':log[:6]},ensure_ascii=False),flush=True)
    pg.close()
  b.close()
