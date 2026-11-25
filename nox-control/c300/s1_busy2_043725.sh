cat > /workspace/nox/tools/s1_busy.py <<'S1PY'
from playwright.sync_api import sync_playwright
import json,time
calls=[]
with sync_playwright() as p:
    b=p.chromium.launch(); ctx=b.new_context(viewport={'width':1440,'height':900}); pg=ctx.new_page()
    errs=[]; pg.on('pageerror',lambda e:errs.append(str(e)[:120]))
    def h(route):
        req=route.request
        if req.url.endswith('/api/turn') and req.method=='POST':
            calls.append(time.time())
            if len(calls)==1:
                route.fulfill(status=200,content_type='application/x-ndjson',body='{"t":"meta","turn_id":"t-x","conversation_id":"c","mode":"fast"}\n{"t":"error","error":"в этом диалоге уже идёт ответ: остановите его или дождитесь","code":"busy"}\n{"t":"done","status":"error"}\n')
                return
        route.continue_()
    pg.route('**/*',h)
    pg.goto('http://localhost:8091/web/chat.html',wait_until='load'); pg.wait_for_timeout(4000)
    pg.evaluate("document.querySelector('#modes [data-m=fast]').click()")
    pg.fill('#input','проверка зависшего хода'); pg.keyboard.press('Enter')
    pg.wait_for_timeout(2500)
    print('BUSY_BUTTON',pg.evaluate("!!document.querySelector('.tg-fix')"),'DRAFT_RESTORED',repr(pg.input_value('#input')))
    pg.click('.tg-fix'); pg.wait_for_timeout(3000)
    print('TURN_CALLS_AFTER_FIX',len(calls))
    for i in range(60):
        pg.wait_for_timeout(2000)
        if not pg.evaluate("document.body.classList.contains('nox-busy')"): break
    t=pg.evaluate("(()=>{const a=[...document.querySelectorAll('#msgs .m.a .txt')].pop();return a?a.innerText:''})()")
    print('FINAL_REPLY',json.dumps(t,ensure_ascii=False)[:160],'ERRS',errs[:3])
    b.close()

S1PY
cd /tmp
timeout 280 /workspace/nox/venv/bin/python /workspace/nox/tools/s1_busy.py 2>&1 | cut -c1-400
