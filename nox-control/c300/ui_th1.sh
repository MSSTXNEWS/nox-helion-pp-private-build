echo "C300: ui_th1"; S=/workspace/nox/web/site; ls -la --time-style=full-iso $S/nox-theme.js $S/nox-wow-bg.js $S/nox-nav.js $S/nox-graphite.css $S/nox-u-ux.js | cut -c20-140; date -u
grep -c graphite $S/nox-theme.js; grep -o "data-nox-theme[^;]\{0,60\}" $S/nox-theme.js | head -3
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/th_graphite/ensure.sh -o /tmp/th_ensure.sh && bash /tmp/th_ensure.sh
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright
/workspace/nox/venv/bin/python - <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); x=b.new_page(); x.goto('http://127.0.0.1:8091/web/system.html',wait_until='domcontentloaded'); x.wait_for_timeout(5000)
    print('THEME',x.evaluate("[document.documentElement.getAttribute('data-nox-theme'),localStorage.getItem('nox.ui.theme'),location.search,[...document.scripts].map(s=>s.src).filter(s=>s.includes('theme')).join()]"))
    b.close()
P
