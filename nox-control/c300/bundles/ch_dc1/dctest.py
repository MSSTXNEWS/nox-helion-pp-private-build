import json,time,base64,textwrap,os
from playwright.sync_api import sync_playwright
U='http://127.0.0.1:8091/web/'
def log(*a): print(*a,flush=True)
with sync_playwright() as p:
    b=p.chromium.launch()
    pg=b.new_page(viewport={'width':1920,'height':1080})
    pg.route('**/api/nox/outbox*',lambda r:r.fulfill(status=200,content_type='application/json',body='{"messages":[]}'))
    errs=[];pg.on('pageerror',lambda e:errs.append(str(e)[:150]))
    pg.goto(U+'chat-dc.html',wait_until='load');pg.evaluate("localStorage.setItem('nox.wow.cur','qa-dct1')");pg.reload();pg.wait_for_timeout(3000)
    log('layout',pg.evaluate("[document.querySelectorAll('sl-split-panel').length,document.querySelectorAll('.lg-layer').length,document.querySelector('.dc-head').offsetHeight,[...document.querySelectorAll('.lg-host')].map(e=>e.className.split(' ')[0]+':'+(e.getAttribute('data-lg-renderer')||'-')).join(',')]"))
    # ghost
    pg.evaluate("window.NOXdcSetInput('Расскажи мне подробно про')");pg.wait_for_timeout(500)
    g=''
    for i in range(24):
        g=pg.evaluate("(document.querySelector('deep-chat').shadowRoot.querySelector('.dc-ghost')||{}).innerText||''")
        if len(g.strip())>len('Расскажи мне подробно про')+2:break
        pg.wait_for_timeout(1000)
    log('ghost',repr(g[:120]))
    if g:
        pg.evaluate("document.querySelector('deep-chat').shadowRoot.querySelector('#text-input').focus()");pg.keyboard.press('Tab');pg.wait_for_timeout(500)
        log('after tab',repr(pg.evaluate("document.querySelector('deep-chat').shadowRoot.querySelector('#text-input').innerText")[:140]))
    pg.evaluate("window.NOXdcSetInput('')")
    # reply
    pg.evaluate("document.querySelector('deep-chat').submitUserMessage({text:'Назови столицу Франции'})")
    for i in range(90):
        if pg.evaluate("!!document.querySelector('deep-chat').shadowRoot.querySelector('.dc-acts-live')"):break
        pg.wait_for_timeout(1000)
    pg.evaluate("[...document.querySelector('deep-chat').shadowRoot.querySelectorAll('.dc-acts button')].find(b=>b.title.indexOf('Ответить')==0).click()");pg.wait_for_timeout(400)
    log('reply preview',pg.evaluate("(document.querySelector('deep-chat').shadowRoot.querySelector('.dc-reply')||{}).innerText"))
    pg.evaluate("document.querySelector('deep-chat').submitUserMessage({text:'а население?'})");pg.wait_for_timeout(1500)
    log('sent',pg.evaluate("JSON.parse(localStorage.getItem('nox.wow.threads')).find(t=>t.id==='qa-dct1').msgs.filter(m=>m.role==='user').map(m=>m.content.slice(0,70))"))
    pg.wait_for_timeout(15000);log('errs',errs[:3]);pg.close()
    # mini 390 overlap
    pg=b.new_page(viewport={'width':390,'height':844},has_touch=True,is_mobile=True)
    pg.goto(U+'settings.html',wait_until='load');pg.wait_for_timeout(4000)
    log('fab cover',pg.evaluate("(()=>{const f=document.querySelector('.nmc-fab');const r=f.getBoundingClientRect();const pts=[[.5,.5],[.2,.2],[.8,.8]].map(a=>{const e=document.elementFromPoint(r.x+r.width*a[0],r.y+r.height*a[1]);return e===f?'fab':(e&&(e.id||e.className&&String(e.className).slice(0,30)||e.tagName))});return [Math.round(r.x),Math.round(r.y),pts]})()"))
    b.close()
