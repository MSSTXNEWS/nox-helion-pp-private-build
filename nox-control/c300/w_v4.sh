echo "C300: w_v4"
N=/workspace/nox; S=$N/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
ok=0; for k in 1 2 3 4 5 6; do t=$(date +%s)$k
 curl -fsSL "$R/w_v3/live_shell.py?cb=$t" -o /tmp/lsh.py; curl -fsSL "$R/w_a11y/nox-a11y-fix.js?cb=$t" -o /tmp/a11y.js
 grep -q nxLiveWow /tmp/lsh.py && grep -q 'sl-button\[size\]' /tmp/a11y.js && { ok=1; break; }; sleep 15; done
[ $ok = 1 ] || { echo STALE; exit 0; }
cp $S/nox-a11y-fix.js $S/nox-a11y-fix.js.bak_v4; cp /tmp/a11y.js $S/nox-a11y-fix.js
python3 /tmp/lsh.py $S/
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$(date +%s)") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$(date +%s)") | tail -1
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
cat > /tmp/v4.py <<'P'
from playwright.sync_api import sync_playwright
J="""()=>[...document.querySelectorAll('sl-button')].filter(b=>b.offsetParent).slice(0,14).map(b=>{const r=b.getBoundingClientRect();const e=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);const o=e&&e!==b&&!b.contains(e)?(e.tagName+'.'+String(e.className).slice(0,24)+'#'+e.id):'ok';return (b.textContent.trim().slice(0,14))+' '+Math.round(r.height)+' '+o})"""
with sync_playwright() as p:
    b=p.chromium.launch(args=['--no-sandbox'])
    for w in (1440,390):
        pg=b.new_page(viewport={'width':w,'height':900})
        try: pg.goto('http://127.0.0.1:18091/web/writer.html',wait_until='load',timeout=60000)
        except Exception as e: print('goto',str(e)[:40])
        pg.wait_for_timeout(5000);print(w,pg.evaluate(J));print('ta',pg.evaluate("[...document.querySelectorAll('textarea')].filter(t=>t.offsetParent).map(t=>Math.round(t.getBoundingClientRect().width))"));pg.close()
    b.close()
P
timeout 120 $N/venv/bin/python /tmp/v4.py 2>&1 | cut -c1-700
