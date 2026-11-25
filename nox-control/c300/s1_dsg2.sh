S=/workspace/nox/web/site
cd $S
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
for f in nox-chat-tg.css nox-chat-tg.js; do cp -p $f $f.bak_s1_$(date +%H%M%S); curl -fsSL "$R/$f?$(date +%s)" -o /tmp/$f && cp /tmp/$f $f && echo OK $f $(wc -c <$f); done
cd /tmp; /workspace/nox/venv/bin/python - <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={'width':1440,'height':900})
    pg.goto('http://localhost:8091/web/chat.html',wait_until='load'); pg.wait_for_timeout(5000)
    print('LI',pg.evaluate("[...document.querySelectorAll('#threadList>li')].slice(0,2).map(l=>l.outerHTML).join('\\n')")[:900])
    print('MODES',pg.evaluate("document.querySelector('#modes').outerHTML")[:500])
    b.close()
P
/workspace/nox/venv/bin/python /workspace/nox/tools/s1_shot.py chat.html tg2 2>&1 | cut -c1-900
