echo "C300: w_u7"
N=/workspace/nox
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
cat > /tmp/u6.py <<'P'
import time,re,sys
from playwright.sync_api import sync_playwright
def run(b,path,abort,args=''):
    pg=b.new_page(viewport={'width':1440,'height':900});t0=time.time();L=[None];D=[None]
    pg.on('load',lambda *_:L.__setitem__(0,round(time.time()-t0,1)));pg.on('domcontentloaded',lambda *_:D.__setitem__(0,round(time.time()-t0,1)))
    if abort: pg.route(re.compile(abort),lambda r:r.abort())
    try: pg.goto('http://127.0.0.1:18091/web/'+path,wait_until='commit',timeout=30000)
    except Exception as e: print('goto',str(e)[:50])
    pg.wait_for_timeout(25000 if L[0] is None else 500)
    print(path,'abort=',abort,'dcl',D[0],'load',L[0]);sys.stdout.flush();pg.close()
with sync_playwright() as p:
    for fl in (['--no-sandbox'],['--no-sandbox','--use-gl=swiftshader','--enable-unsafe-swiftshader']):
        b=p.chromium.launch(args=fl);print('flags',len(fl))
        run(b,'settings.html',None); run(b,'chat-dc.html',None); run(b,'chat-dc.html',r'nox-theme\.js|nox-worlds|nox-fx'); run(b,'chat-dc.html',r'vendor/shoelace')
        b.close()
P
timeout 280 $N/venv/bin/python /tmp/u6.py 2>&1 | cut -c1-300
