echo "K1: v1d_qa"
N=/workspace/nox; export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
cat > /tmp/v1dqa.py <<'P'
from playwright.sync_api import sync_playwright
import time
with sync_playwright() as p:
    b=p.chromium.launch(args=['--no-sandbox','--use-gl=swiftshader','--enable-unsafe-swiftshader'])
    pg=b.new_page(viewport={'width':1440,'height':900});errs=[]
    pg.on('pageerror',lambda e:errs.append(str(e)[:120]))
    pg.goto('http://127.0.0.1:18091/web/chat-v1d.html',wait_until='load');pg.evaluate("localStorage.clear()");pg.reload();pg.wait_for_timeout(3000)
    print('sun',pg.evaluate("document.querySelector('.sun')&&document.querySelector('.sun').dataset.s"),'footer',pg.evaluate("document.querySelector('footer')&&document.querySelector('footer').innerText.slice(0,80)"))
    # обычный ход
    t0=time.time();pg.fill('textarea','Привет, коротко: как дела?');pg.keyboard.press('Enter')
    seen=set()
    for i in range(120):
        s=pg.evaluate("document.querySelector('.sun')&&document.querySelector('.sun').dataset.s");seen.add(s)
        if time.time()-t0>3 and s=='ОЖИДАНИЕ':break
        pg.wait_for_timeout(500)
    print('turn states',sorted(x for x in seen if x),'%.1fs'%(time.time()-t0))
    print('answer',pg.evaluate("(()=>{const e=[...document.querySelectorAll('.nox-body')].pop();return e?e.innerText.slice(0,160):'NONE'})()"))
    print('meta',pg.evaluate("(()=>{const e=[...document.querySelectorAll('.nox-msg')].pop();return e?e.innerText.split('\\n').slice(-3).join(' | ').slice(0,200):''})()"))
    print('tags',pg.evaluate("[...document.querySelectorAll('[aria-label=\"Быстрые ответы\"] button')].map(e=>e.textContent).slice(0,5)"))
    # рисование
    t0=time.time();pg.fill('textarea','нарисуй простой красный круг на белом фоне');pg.keyboard.press('Enter')
    ok=False
    for i in range(180):
        if pg.evaluate("!!document.querySelector('figure img')"):ok=True;break
        if pg.evaluate("document.body.innerText.includes('Не получилось нарисовать')"):break
        pg.wait_for_timeout(500)
    dt=time.time()-t0
    print('DRAW ok',ok,'%.1fs'%dt)
    if ok:
        pg.wait_for_timeout(1500)
        print('img',pg.evaluate("(()=>{const i=document.querySelector('figure img');return [i.complete,i.naturalWidth,i.naturalHeight,i.src.slice(-60)]})()"))
    else:
        print(pg.evaluate("(()=>{const e=[...document.querySelectorAll('.nox-body')].pop();return e?e.innerText.slice(0,200):'NONE'})()"))
    print('errs',errs[:5]);b.close()
P
echo "--- direct turn"; t0=$(date +%s); curl -sN -m 60 -X POST http://127.0.0.1:18091/api/turn -H 'Content-Type: application/json' -d '{"conversation_id":"dzq3","message":"Привет","mode":"auto","length":"normal","source":"full"}' | cut -c1-160 | head -6; echo "turn $(( $(date +%s)-t0 ))s"
echo "--- direct img"; t0=$(date +%s); curl -s -m 100 -w ' code=%{http_code}' -X POST http://127.0.0.1:18091/img/generate -H 'Content-Type: application/json' -d '{"prompt":"red circle on white background","width":512,"height":512}' | cut -c1-300; echo " img $(( $(date +%s)-t0 ))s"
timeout 280 $N/venv/bin/python /tmp/v1dqa.py 2>&1 | cut -c1-400
