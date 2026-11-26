import sys,os,json,time,signal
class TO(Exception): pass
def _h(*a): raise TO('watchdog 200s')
signal.signal(signal.SIGALRM,_h)
from playwright.sync_api import sync_playwright
BASE='http://127.0.0.1:18091/web/chat-dc.html'
OUT='/workspace/nox/state/rv'
SR="document.querySelector('deep-chat').shadowRoot"
def L(): return "(()=>{var s=%s;return s?s.textContent.length:-1})()"%SR
with sync_playwright() as p:
  b=p.chromium.launch(args=['--use-gl=swiftshader','--enable-unsafe-swiftshader'])
  for w,h in ((390,844),(1440,900),(1920,1080)):
    res={'w':w}
    signal.alarm(200)
    try:
      mob=w<500
      c=b.new_context(viewport={'width':w,'height':h},has_touch=mob,is_mobile=mob); pg=c.new_page(); errs=[]
      pg.on('pageerror',lambda e:errs.append('PE '+str(e)[:140]))
      pg.on('response',lambda r:errs.append('HTTP%d %s'%(r.status,r.url.split('18091')[-1][:70])) if r.status>=400 else None)
      net=[]
      pg.on('response',lambda r:net.append('%d %s %s'%(r.status,r.request.method,r.url.split('18091')[-1][:60])) if r.request.method=='POST' or '/api/' in r.url or '/v1/' in r.url else None)
      pg.route('**/api/nox/outbox*',lambda r:r.fulfill(status=200,content_type='application/json',body='{"messages":[]}'))
      pg.set_default_timeout(30000); pg.goto(BASE,wait_until='load',timeout=30000); pg.evaluate("localStorage.setItem('nox.wow.cur','qa-rv%d')"%w); pg.reload(); pg.wait_for_timeout(3000)
      res['geom']=pg.evaluate("(()=>{var dc=document.querySelector('deep-chat');var r=dc.getBoundingClientRect();var ta=%s.querySelector('#text-input,[contenteditable]');var t=ta?ta.getBoundingClientRect():null;return {dc:[Math.round(r.x),Math.round(r.y),Math.round(r.width),Math.round(r.height)],input:t?[Math.round(t.x),Math.round(t.y),Math.round(t.width),Math.round(t.height)]:null,vh:innerHeight}})()"%SR)
      for tag,q in (('text','Объясни в двух предложениях, что такое энтропия'),('draw','Нарисуй кота-астронавта')):
        l0=pg.evaluate(L()); i0=pg.evaluate("%s.querySelectorAll('img,canvas,svg image').length"%SR)
        t0=time.time(); pg.evaluate("document.querySelector('deep-chat').submitUserMessage({text:%s})"%json.dumps(q))
        first=None; last=l0; stable=0
        for i in range(180 if tag=='draw' else 120):
          pg.wait_for_timeout(500); l=pg.evaluate(L())
          if first is None and l>l0+len(q)+5: first=round(time.time()-t0,1)
          if first is not None and l==last: stable+=1
          else: stable=0
          last=l
          imgs=pg.evaluate("%s.querySelectorAll('img,canvas').length"%SR)
          if tag=='text' and first is not None and stable>=6: break
          if tag=='draw' and imgs>i0 and stable>=4: break
        res[tag]={'first_s':first,'total_s':round(time.time()-t0,1),'delta_chars':last-l0,'imgs_new':pg.evaluate("%s.querySelectorAll('img,canvas').length"%SR)-i0}
        pg.screenshot(path='%s/chatfn_%s_%d.jpg'%(OUT,tag,w),type='jpeg',quality=72)
      res['net']=[n for n in net if 'outbox' not in n][-14:]; res['errs']=errs[:8]; c.close()
    except BaseException as e:
      res['fatal']=repr(e)[:200]
      try: c.close()
      except BaseException: pass
    signal.alarm(0)
    print(json.dumps(res,ensure_ascii=False),flush=True)
  b.close()
