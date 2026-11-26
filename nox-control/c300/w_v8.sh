echo "C300: w_v8"
N=/workspace/nox; S=$N/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
ok=0; for k in $(seq 1 14); do t=$(date +%s)$k
 curl -fsSL "$R/ch_dc1/nox-dc-fill.js?cb=$t" -o /tmp/fill.js; curl -fsSL "$R/w_v8/nox-reveal.js?cb=$t" -o /tmp/rev.js
 grep -q 'top:36%' /tmp/fill.js && grep -q 'getAnimations' /tmp/rev.js && { ok=1; break; }; sleep 20; done
[ $ok = 1 ] || { echo STALE; exit 0; }
cp /tmp/fill.js $S/nox-dc-fill.js; cp /tmp/rev.js $S/nox-reveal.js
python3 - <<'P'
S='/workspace/nox/web/site/'
def tag(pg,js):
    try: h=open(S+pg).read()
    except Exception: print('no',pg); return
    if js in h: return
    open(S+pg+'.bak_v8','w').write(h); open(S+pg,'w').write(h.replace('</body>','<script src="./%s?v=v8" defer></script></body>'%js,1) if '</body>' in h else h+'<script src="./%s?v=v8" defer></script>'%js); print('tag',pg,js)
tag('chat-dc.html','nox-dc-fill.js')
for pg in ('writer','system','memory','settings','studio','photo','training','voice','live','calls','intents'): tag(pg+'.html','nox-reveal.js')
P
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$(date +%s)") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$(date +%s)") | tail -1
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
cat > /tmp/v8.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(args=['--no-sandbox'])
    pg=b.new_page(viewport={'width':390,'height':844})
    try: pg.goto('http://127.0.0.1:18091/web/studio.html',wait_until='load',timeout=60000)
    except Exception as e: print('goto',str(e)[:40])
    pg.wait_for_timeout(8000)
    print('studio',pg.evaluate("""()=>{const out=[];const w=document.createTreeWalker(document.body,NodeFilter.SHOW_ELEMENT);let n;while(n=w.nextNode()){if(n.children.length==0&&/^(Без стиля|Кино)$/.test((n.textContent||'').trim())&&n.offsetParent){let e=n;for(let i=0;i<4&&e;i++){const cs=getComputedStyle(e);out.push(e.tagName+'.'+String(e.className).slice(0,30)+'#'+e.id+' d='+cs.display+' ox='+cs.overflowX+' fs='+cs.flexShrink+' w='+Math.round(e.getBoundingClientRect().width)+' sw='+e.scrollWidth);e=e.parentElement}break}}return out}"""))
    pg=b.new_page(viewport={'width':1920,'height':1080});pg.goto('http://127.0.0.1:18091/web/chat-dc.html',wait_until='load',timeout=60000);pg.wait_for_timeout(6000)
    print('fill',pg.evaluate("[!!document.getElementById('dcFill'),document.querySelectorAll('#dcFill button').length,getComputedStyle(document.getElementById('dcFill')).display]"))
    b.close()
P
timeout 150 $N/venv/bin/python /tmp/v8.py 2>&1 | cut -c1-700
