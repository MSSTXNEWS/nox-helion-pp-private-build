import sys,time,json
from playwright.sync_api import sync_playwright
URL="http://127.0.0.1:8091/web/chat.html"; OUT="/workspace/nox/web/site/qa/"
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={"width":1440,"height":900}); pg.goto(URL); pg.wait_for_timeout(5000)
    print("body:",pg.evaluate("()=>document.body.className")[:100], "cxk:",pg.evaluate("()=>document.querySelectorAll('.cxk-t').length"))
    pg.click("sl-textarea.tg-slta"); pg.keyboard.type("Какая столица Австралии?"); pg.keyboard.press("Enter")
    t0=time.time(); st=None
    while time.time()-t0<200:
        pg.wait_for_timeout(3000)
        st=pg.evaluate("()=>({j:[...document.querySelectorAll('.rq-judge')].map(e=>e.textContent),t:document.querySelectorAll('.rq-think').length,b:[...document.querySelectorAll('.rq-meta sl-badge')].map(e=>e.textContent),a:document.querySelectorAll('#feed .m.a').length})")
        if any('судьями' in x or 'проверку' in x for x in st['j']) and not any('проверяется' in x for x in st['j']): break
    print("meta after %.0fs:"%(time.time()-t0), json.dumps(st,ensure_ascii=False))
    pg.screenshot(path=OUT+"c_live_meta.png")
    # ответить
    n0=pg.evaluate("()=>document.querySelectorAll('#msgs .m').length")
    a=pg.query_selector_all("#feed .m.a"); 
    if a:
        a[-1].hover(); btn=a[-1].query_selector(".rq-act")
        print("reply btn:", bool(btn))
        if btn:
            btn.click(); pg.wait_for_timeout(500); print("plate visible:", pg.evaluate("()=>{const p=document.querySelector('.rq-plate');return !!p&&!p.hidden}"))
            pg.click("sl-textarea.tg-slta"); pg.keyboard.type("А почему?"); pg.keyboard.press("Enter"); pg.wait_for_timeout(4000)
            print("quote in feed:", pg.evaluate("()=>[...document.querySelectorAll('.rq-in')].map(e=>e.textContent.slice(0,80))"), "plate hidden after send:", pg.evaluate("()=>{const p=document.querySelector('.rq-plate');return !p||p.hidden}"))
    pg.screenshot(path=OUT+"c_live_reply.png"); b.close()
