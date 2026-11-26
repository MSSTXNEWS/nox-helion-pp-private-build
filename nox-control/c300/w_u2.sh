echo "C300: w_u2"
N=/workspace/nox
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
cat > /tmp/u1.py <<'P'
from playwright.sync_api import sync_playwright
J="""()=>[...document.querySelectorAll('a,button,[role=button],input,summary,select')].filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&getComputedStyle(e).visibility!='hidden'&&(r.width<43||r.height<43)}).slice(0,12).map(e=>e.tagName+'.'+e.className.toString().slice(0,30)+'#'+e.id+' '+Math.round(e.getBoundingClientRect().width)+'x'+Math.round(e.getBoundingClientRect().height))"""
with sync_playwright() as p:
    b=p.chromium.launch(args=['--no-sandbox','--use-gl=swiftshader','--enable-unsafe-swiftshader'])
    for pg_,w in (('training',1440),('intents',390),('index',1440)):
        try:
            pg=b.new_page(viewport={'width':w,'height':900});errs=[];pg.on('pageerror',lambda e:errs.append(str(e)[:80]))
            pg.goto('http://127.0.0.1:18091/web/%s.html'%pg_,wait_until='commit',timeout=90000);pg.wait_for_timeout(15000)
            extra=pg.evaluate("(document.querySelector('#nxTB')||{textContent:'-'}).textContent.slice(0,90)") if pg_=='training' else ''
            r=pg.evaluate(J);print(pg_,w,len(r),r[:8],extra,errs[:2])
        except Exception as e: print(pg_,w,'ERR',str(e)[:80])
    b.close()
P
timeout 250 $N/venv/bin/python /tmp/u1.py 2>&1 | cut -c1-400
