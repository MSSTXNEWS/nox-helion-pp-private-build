import sys,time,base64
from playwright.sync_api import sync_playwright
U='http://127.0.0.1:%s/web/chat.html'
import os
port=os.environ.get('NOXPORT','8080')
with sync_playwright() as p:
    b=p.chromium.launch()
    for w,h,m in [(1920,1080,0),(2560,1440,0),(390,844,1)]:
        pg=b.new_page(viewport={'width':w,'height':h},has_touch=bool(m),is_mobile=bool(m))
        errs=[];pg.on('pageerror',lambda e:errs.append(str(e)[:150]))
        pg.goto(U%port,wait_until='load');pg.wait_for_timeout(3000);print(w,'url',pg.url)
        pg.evaluate("localStorage.setItem('nox.wow.cur','qa-dc%d')"%w);pg.reload();pg.wait_for_timeout(2500)
        t0=time.time();pg.evaluate("document.querySelector('deep-chat').submitUserMessage({text:'как дела'})")
        first=None
        for i in range(120):
            n=pg.evaluate("(()=>{const r=document.querySelector('deep-chat').shadowRoot;const a=[...r.querySelectorAll('.ai-message-text')].pop();return a?a.innerText.length:0})()")
            if n>0 and first is None and pg.evaluate("document.querySelector('deep-chat').shadowRoot.querySelectorAll('.ai-message-text').length")>=2: first=time.time()-t0
            if pg.evaluate("!!document.querySelector('deep-chat').shadowRoot.querySelector('.dc-acts-live')"):break
            pg.wait_for_timeout(500)
        print(w,'first',first,'total',round(time.time()-t0,1),pg.evaluate("[document.querySelector('.dc-head').offsetHeight,document.documentElement.getAttribute('data-nox-theme'),[...document.querySelector('deep-chat').shadowRoot.querySelectorAll('.ai-message-text')].pop().innerText.slice(0,200)]"),errs[:2])
        pg.screenshot(path='/tmp/dc%d.jpg'%w,type='jpeg',quality=60)
        if w!=2560: print('B64BEGIN');print(base64.b64encode(open('/tmp/dc%d.jpg'%w,'rb').read()).decode()[:0]);print('B64END')
        pg.close()
    b.close()
