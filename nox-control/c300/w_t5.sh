echo "C300: w_t5"
N=/workspace/nox; S=$N/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
ok=0; for k in 1 2 3 4 5 6 7 8; do t=$(date +%s)$k
 curl -fsSL "$R/w_roles/nox-roles-x2.js?cb=$t" -o /tmp/x2.js; curl -fsSL "$R/w_bridge/api_bridge.py?cb=$t" -o /tmp/br.py
 grep -q 'sci/semantic' /tmp/x2.js && grep -q 'sci_semantic' /tmp/br.py && { ok=1; break; }; sleep 15; done
[ $ok = 1 ] || { echo STALE; exit 0; }
B=$N/ops/api_bridge/api_bridge.py; cp $B $B.bak_t5; cp /tmp/br.py $B; supervisorctl restart nox_api_bridge | tail -1
cp /tmp/x2.js $S/nox-roles-x2.js
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$(date +%s)") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$(date +%s)") | tail -1
sleep 3
python3 - <<'P'
import json,urllib.request
def shape(o,p=''):
    if isinstance(o,dict):
        for k,v in o.items(): shape(v,p+'.'+k)
    elif isinstance(o,list): print('SHAPE',p,'list',len(o))
    else: print('SHAPE',p,type(o).__name__,len(str(o)))
for u in ('self_now','briefs'):
    d=json.load(urllib.request.urlopen('http://127.0.0.1:8796/api/nox/'+u,timeout=10))
    d.pop('ts',None); print(u); shape(d.get('data') if u=='self_now' else {k:(v.get('data') if isinstance(v,dict) else None) or v.get('hold') for k,v in d.items() if k in('morning','evening')})
P
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
cat > /tmp/t5.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(args=['--no-sandbox','--use-gl=swiftshader','--enable-unsafe-swiftshader']);pg=b.new_page(viewport={'width':1440,'height':900});errs=[];pg.on('pageerror',lambda e:errs.append(str(e)[:100]))
    pg.goto('http://127.0.0.1:18091/web/chat-dc.html',wait_until='load');pg.wait_for_timeout(7000)
    print('now card len',pg.evaluate("(document.querySelector('#dcNow div')||{textContent:'-'}).textContent.length"),pg.evaluate("(document.querySelector('#dcNow div')||{textContent:''}).textContent.slice(0,14)"),errs)
    pg.goto('http://127.0.0.1:18091/web/writer.html?role=scientist',wait_until='load');pg.wait_for_timeout(4500)
    pg.evaluate("document.querySelector('.rx2-t[data-s=semantic]').click();const q=document.getElementById('rx2-q');q.value='entropy';document.getElementById('rx2-go').click()");pg.wait_for_timeout(9000)
    print('semantic',pg.evaluate("[document.getElementById('rx2-ss').textContent,document.querySelectorAll('#rx2-res sl-card').length]"))
    b.close()
P
timeout 100 $N/venv/bin/python /tmp/t5.py 2>&1 | cut -c1-200
