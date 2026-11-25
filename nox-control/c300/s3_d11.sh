S=/workspace/nox/web/site; P=/workspace/nox/web/pkg/server; PY=/workspace/nox/venv/bin/python
echo "== D11"; sed -n 166,180p $P/nox_cmd.py | cut -c1-250
echo "-- fixed"; ls -l $S/qa/rework/ | head -20; wc -c $S/qa/rework/nav.fixed; head -c 300 $S/qa/rework/nav.fixed; find /workspace/nox -name "nav.fixed" -not -path "*/node_modules/*" 2>/dev/null; grep -rn "\.fixed" /workspace/nox/state/*.md /workspace/nox/web/*.md 2>/dev/null | head -5 | cut -c1-200
echo "-- sw"; ls $S/sw*.js $S/service-worker*.js 2>/dev/null; grep -n "CACHE\|cache" $S/sw.js 2>/dev/null | head -8 | cut -c1-200; grep -n "serviceWorker" $S/nox-pwa.js | head -3 | cut -c1-200
cat > /tmp/s3_d11.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch()
    for w in (1280,1440,1920):
        ctx=b.new_context(viewport={'width':w,'height':900},service_workers='block'); pg=ctx.new_page()
        css=[]; pg.on('response',lambda r: css.append(r.url.split('/')[-1][:40]+':'+r.headers.get('cache-control','-')[:14]) if r.url.endswith(('.css','nox-nav-x.js','nox-menu-x.css')) and 'nox-' in r.url else None)
        pg.goto('http://localhost:8091/web/music.html',wait_until='load'); pg.wait_for_timeout(4000)
        print(w, pg.evaluate("()=>{const r=[...document.querySelectorAll('.tb-l > *')].filter(c=>getComputedStyle(c).display!='none').map(c=>Math.round(c.getBoundingClientRect().left));const c=document.getElementById('nxx-crumb');return {minLeft:Math.min(...r),n:r.length,crumb:c&&c.textContent,disp:[...document.querySelectorAll('.tb-l > *')].map(e=>e.dataset.k+':'+getComputedStyle(e).display).join(',')}}"))
        if w==1280: print(css)
        ctx.close()
    b.close()
P
timeout 150 $PY -I /tmp/s3_d11.py 2>&1 | cut -c1-900
