echo "C300: w_v7"
N=/workspace/nox; export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
cat > /tmp/v7.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(args=['--no-sandbox'])
    def pgo(n,w=390):
        pg=b.new_page(viewport={'width':w,'height':844})
        try: pg.goto('http://127.0.0.1:18091/web/%s.html'%n,wait_until='load',timeout=60000)
        except Exception as e: print(n,'goto',str(e)[:40])
        pg.wait_for_timeout(5000);return pg
    pg=pgo('settings');print('settings',pg.evaluate("""()=>{const h=document.querySelector('h1'),k=document.querySelector('a.nox-worlds-open');if(!h||!k)return 'no';const a=h.getBoundingClientRect(),c=k.getBoundingClientRect();return ['h1',Math.round(a.top),Math.round(a.bottom),'link',Math.round(c.top),Math.round(c.bottom),'overlap',a.top<c.bottom&&a.bottom>c.top&&a.left<c.right&&a.right>c.left]}"""))
    pg=pgo('studio');print('studio chips',pg.evaluate("[...document.querySelectorAll('#stP sl-button')].slice(0,5).map(x=>Math.round(x.getBoundingClientRect().width))"))
    pg=pgo('live');print('live sub',pg.evaluate("(document.getElementById('ts')||{textContent:'-'}).textContent.slice(0,30)"),pg.evaluate("!!document.querySelector('#nxLiveWow')"),pg.evaluate("document.querySelectorAll('#app .card').length"))
    pg=pgo('chat-dc');print('chat head bg',pg.evaluate("getComputedStyle(document.getElementById('dcHead')).backdropFilter.slice(0,20)"))
    b.close()
P
timeout 150 $N/venv/bin/python /tmp/v7.py 2>&1 | cut -c1-300
