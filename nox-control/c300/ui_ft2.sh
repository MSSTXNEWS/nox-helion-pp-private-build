echo "C300: ui_ft2 (шрифты пакета V29.3)"
S=/workspace/nox/web/site; V=/workspace/nox/web/v29src/V29_3_FROZEN/site
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
du -sh $V/pc/vendor/fonts $V/pc/pages/_vendor/fonts
for d in pc/vendor/fonts vendor/fonts pc/pages/_vendor/fonts pages/_vendor/fonts _vendor/fonts; do mkdir -p $S/$d; done
cp -an $V/pc/vendor/fonts/. $S/pc/vendor/fonts/; cp -an $V/pc/vendor/fonts/. $S/vendor/fonts/
cp -an $V/pc/pages/_vendor/fonts/. $S/pc/pages/_vendor/fonts/; cp -an $V/pc/pages/_vendor/fonts/. $S/pages/_vendor/fonts/; cp -an $V/pc/pages/_vendor/fonts/. $S/_vendor/fonts/
cat > /tmp/ft.py <<'PEOF'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch()
    for pg in ('studio','index','settings'):
        x=b.new_page(); bad=[]
        x.on('response',lambda r:bad.append(str(r.status)+' '+r.url.replace('http://127.0.0.1:8091','')) if r.status>=400 and '/api/' not in r.url else None)
        x.goto('http://127.0.0.1:8091/web/%s.html'%pg,wait_until='domcontentloaded',timeout=60000); x.wait_for_timeout(4000)
        print('FT',pg,bad[:6],flush=True); x.close()
    b.close()
PEOF
timeout 120 $PY /tmp/ft.py
