echo "K1: v1d_qa2"
N=/workspace/nox; export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
cat > /tmp/v1dqa2.py <<'P'
from playwright.sync_api import sync_playwright
import time
TA='textarea:not([aria-hidden])'
with sync_playwright() as p:
    b=p.chromium.launch(args=['--no-sandbox','--use-gl=swiftshader','--enable-unsafe-swiftshader'])
    pg=b.new_page(viewport={'width':1440,'height':900});errs=[];reqs=[]
    pg.on('pageerror',lambda e:errs.append(str(e)[:120]))
    pg.on('response',lambda r:reqs.append((r.url.split('8091')[-1][:40],r.status)) if ('/img/' in r.url or 'memory' in r.url) else None)
    pg.goto('http://127.0.0.1:18091/web/chat-dc.html',wait_until='load');pg.evaluate("localStorage.clear()");pg.reload();pg.wait_for_timeout(3000)
    print('dc ab1d',pg.evaluate("[...document.scripts].some(s=>/ab1d/.test(s.src))"),'sun',pg.evaluate("document.querySelector('.sun')&&document.querySelector('.sun').dataset.s"))
    t0=time.time();pg.fill(TA,'нарисуй простой красный круг на белом фоне');pg.keyboard.press('Enter');pg.wait_for_timeout(1500)
    print('skeleton',pg.evaluate("!!document.querySelector('.draw-sk')"),'sun',pg.evaluate("document.querySelector('.sun').dataset.s"),'strip',pg.evaluate("document.querySelector('[role=status][aria-live]')&&document.querySelector('[role=status][aria-live]').innerText.replace(/\\n/g,' ')"))
    ok=False
    for i in range(200):
        if pg.evaluate("!!document.querySelector('figure img')"):ok=True;break
        if pg.evaluate("document.body.innerText.includes('Не получилось нарисовать')"):break
        pg.wait_for_timeout(500)
    print('DRAW ok',ok,'%.1fs'%(time.time()-t0))
    if ok:
        pg.wait_for_timeout(1500)
        print('img',pg.evaluate("(()=>{const i=document.querySelector('figure img');return [i.complete,i.naturalWidth,i.naturalHeight]})()"))
        pg.screenshot(path='/tmp/draw.png')
        pg.click('figure >> text=Увеличить');pg.wait_for_timeout(400);print('lightbox',pg.evaluate("!!document.querySelector('[role=dialog] img')"));pg.keyboard.press('Escape');pg.wait_for_timeout(400);print('lb closed',not pg.evaluate("!!document.querySelector('[role=dialog] img')"))
        print('download href',pg.evaluate("document.querySelector('figure a[download]').getAttribute('href').slice(0,40)"))
        pg.click('figure >> text=В блокнот');print('notebook',pg.evaluate("(localStorage.getItem('nox.ab.notes')||'').slice(0,60)"))
        print('before var imgs',pg.evaluate("document.querySelectorAll('figure img').length"))
        pg.click('figure >> text=Вариации')
        for i in range(200):
            if pg.evaluate("document.querySelectorAll('figure img').length")>=2:break
            pg.wait_for_timeout(500)
        print('variation imgs',pg.evaluate("document.querySelectorAll('figure img').length"))
    else: print(pg.evaluate("(()=>{const e=[...document.querySelectorAll('.nox-body')].pop();return e?e.innerText.slice(0,200):'NONE'})()"))
    # теги + Tab
    pg.fill(TA,'Привет, коротко: как дела?');pg.keyboard.press('Enter')
    for i in range(160):
        if pg.evaluate("document.querySelector('.sun').dataset.s")=='ОЖИДАНИЕ' and i>6:break
        pg.wait_for_timeout(500)
    tags=pg.evaluate("[...document.querySelectorAll('[aria-label=\"Быстрые ответы\"] button')].map(e=>e.textContent)");print('tags',tags)
    if tags:
        pg.click('[aria-label="Быстрые ответы"] button');pg.wait_for_timeout(500);print('tag->composer/sent',repr(pg.input_value(TA))[:60],pg.evaluate("document.querySelectorAll('.owner-msg').length"))
    pg.fill(TA,'расскажи мне про');pg.wait_for_timeout(2500)
    print('draft',pg.evaluate("(()=>{const e=[...document.querySelectorAll('kbd')].find(k=>k.textContent==='Tab');return e?e.parentElement.innerText.slice(0,100):'(пусто)'})()"))
    print('mem reqs',reqs[-6:],'errs',errs[:4]);b.close()
P
timeout 420 $N/venv/bin/python /tmp/v1dqa2.py 2>&1 | tail -60
