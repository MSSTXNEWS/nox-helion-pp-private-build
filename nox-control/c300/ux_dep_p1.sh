echo "C300: ux_dep_p1"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; export PATH=/workspace/nox/tools/node/bin:$PATH
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/61dcf4315d3744e8191ba3a7e95e2aed15017695/nox-control/c300/bundles/ux_p1
curl -fsSL --retry 5 --retry-delay 4 --retry-all-errors $RAW/patch.py -o /tmp/ux_p1_patch.py || { echo FAIL_FETCH; exit 0; }
mkdir -p vendor/nox-extra/images; [ -f vendor/nox-extra/images/marker-shadow.png ] || curl -fsSL --retry 5 $RAW/vendor/nox-extra/images/marker-shadow.png -o vendor/nox-extra/images/marker-shadow.png
python3 /tmp/ux_p1_patch.py ux$TS
for f in nox-p-system.js nox-k6-dash.js nox-k6-canvasdoc.js nox-k6-board.js nox-k6-mindmap.js nox-s6-cinema.js; do node --check $f && echo "OK $f" || { cp $f.bak_ux_ux$TS $f 2>/dev/null; echo "ROLLBACK $f"; }; done
grep -c "layout-grid" nox-k6-dash.js; grep -c "12px/1.3" nox-pages.css
echo "== живая проверка"
cat > /tmp/ux_p1_qa.py <<'PYX'
import sys
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch()
    for pg in ['system','widgets','memory','map','cinema','knowledge']:
        for w in (1440,390):
            c=b.new_context(viewport={'width':w,'height':850});g=c.new_page();er=[];bad=[]
            g.on('pageerror',lambda e:er.append(str(e)[:100]))
            g.on('response',lambda r:bad.append(str(r.status)+' '+r.url[-60:]) if r.status>=400 and ('tabler' in r.url or 'marker' in r.url) else None)
            try:
                g.goto('http://127.0.0.1:8091/'+pg+'.html',wait_until='load',timeout=25000);g.wait_for_timeout(2500)
                hs=g.evaluate('document.documentElement.scrollWidth-innerWidth')
            except Exception as e: hs='ERR '+str(e)[:60]
            print('QA',pg,w,'hscroll',hs,'EXC' if er else 'ok',er[:2],bad[:3])
            c.close()
    b.close()
PYX
timeout 150 /workspace/nox/venv/bin/python /tmp/ux_p1_qa.py | tee /tmp/ux_p1_qa.out
grep -E "^QA.*(EXC|Unexpected)" /tmp/ux_p1_qa.out && { for f in nox-p-system.js nox-k6-dash.js nox-k6-canvasdoc.js nox-k6-board.js nox-k6-mindmap.js nox-s6-cinema.js nox-pages.css nox-hud-s1.css; do b=$(ls -t $f.bak_ux_ux$TS 2>/dev/null|head -1); [ -n "$b" ] && cp $b $f; done; echo ROLLBACK_ALL; } || echo QA_CLEAN
echo done
