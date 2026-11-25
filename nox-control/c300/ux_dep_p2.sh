echo "C300: ux_dep_p2"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; export PATH=/workspace/nox/tools/node/bin:$PATH
curl -fsSL --retry 5 --retry-delay 4 --retry-all-errors https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/918ec205242d9e0741ac86f96dc5a4d95b0298eb/nox-control/c300/bundles/ux_p2/patch.py -o /tmp/ux_p2_patch.py || { echo FAIL_FETCH; exit 0; }
python3 /tmp/ux_p2_patch.py ux$TS
for f in nox-p-projects.js nox-k6-slides.js; do node --check $f && echo "OK $f" || { cp $f.bak_ux_ux$TS $f; echo "ROLLBACK $f"; }; done
cat > /tmp/ux_p2_qa.py <<'PYX'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch()
    for pg in ['projects','pdf','atlas']:
        for w in (1440,390):
            c=b.new_context(viewport={'width':w,'height':850});g=c.new_page();er=[]
            g.on('pageerror',lambda e:er.append(str(e)[:100]))
            try:
                g.goto('http://127.0.0.1:8091/'+pg+'.html',wait_until='load',timeout=25000);g.wait_for_timeout(2500)
                hs=g.evaluate('document.documentElement.scrollWidth-innerWidth')
            except Exception as e: hs='ERR'
            print('QA',pg,w,'hscroll',hs,'EXC' if er else 'ok',er[:2]);c.close()
    b.close()
PYX
timeout 120 /workspace/nox/venv/bin/python /tmp/ux_p2_qa.py | tee /tmp/ux_p2_qa.out
grep -E "^QA.*EXC" /tmp/ux_p2_qa.out && { for f in projects.html nox-p-projects.js nox-atlas-s1.css nox-k6-slides.js; do b=$(ls -t $f.bak_ux_ux$TS 2>/dev/null|head -1); [ -n "$b" ] && cp $b $f; done; echo ROLLBACK_ALL; } || echo QA_CLEAN
