import json
from playwright.sync_api import sync_playwright
URL="http://127.0.0.1:8091/web/chat.html"; OUT="/workspace/nox/web/site/qa/"
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={"width":1440,"height":900}); pg.goto(URL); pg.wait_for_timeout(7000)
    print("demo:",pg.evaluate("()=>({msgs:document.querySelectorAll('#feed .m').length,judge:[...document.querySelectorAll('.rq-judge')].map(e=>e.textContent),think:document.querySelectorAll('.rq-think').length,badges:[...document.querySelectorAll('.rq-meta sl-badge')].map(e=>e.textContent),more:document.querySelectorAll('.cw-more').length,bw:(document.querySelector('#feed .m.a .bubble')||{getBoundingClientRect:()=>({width:0})}).getBoundingClientRect().width})"))
    pg.screenshot(path=OUT+"c_demo_1440.png")
    a=pg.query_selector_all("#feed .m.a")
    if a:
        a[-1].hover(); btn=a[-1].query_selector(".rq-act"); print("reply btn:",bool(btn))
        if btn:
            btn.click()
            for ms in (300,700,1500):
                pg.wait_for_timeout(ms); print("plate@%d:"%ms, pg.evaluate("()=>{const p=document.querySelector('.rq-plate');return p?{hidden:p.hidden,disp:getComputedStyle(p).display,w:p.getBoundingClientRect().width}:null}"))
        pg.evaluate("()=>{const t=document.querySelector('#feed .m.a .bubble .txt');const r=document.createRange();r.selectNodeContents(t.firstElementChild||t);const s=getSelection();s.removeAllRanges();s.addRange(r);document.dispatchEvent(new Event('selectionchange'))}"); pg.wait_for_timeout(700)
        print("quote btn:",pg.evaluate("()=>{const q=document.querySelector('.rq-qb');return q?{hidden:q.hidden}:null}"))
    pg.screenshot(path=OUT+"c_reply_1440.png"); b.close()
