#!/bin/bash
# t_2.sh (исполнитель T): ставит оверлей nox-chat-tg.css/.js на чат, отправляет «привет», снимает скриншоты ПК и моб.
# Бэкап chat.html -> chat.html.bak_t_1. Ничего не удаляет.
set -u
W=/workspace/nox
S=$W/web/site
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/t_assets
cd $S || exit 1
for f in nox-chat-tg.css nox-chat-tg.js; do
  curl -fsSL "$RAW/$f" -o "$f.new" && mv "$f.new" "$f" && echo "got $f" || echo "FAIL $f"
done
[ -f chat.html.bak_t_1 ] || cp chat.html chat.html.bak_t_1
python3 -I - "$S/chat.html" <<'P'
import sys
p = sys.argv[1]; s = open(p, encoding='utf-8').read()
css = '<link rel="stylesheet" href="./nox-chat-tg.css?v=1">'
js = '<script type="module" src="./nox-chat-tg.js?v=1"></script>'
if 'nox-chat-tg.css' not in s:
    a = '<link rel="stylesheet" href="./vendor/nox-chat-ui/nui.css">'
    assert s.count(a) == 1, 'nui anchor'
    s = s.replace(a, a + css, 1)
if 'nox-chat-tg.js' not in s:
    a = '<script type="module" src="./vendor/nox-chat-ui/chat-ui.js"></script>'
    assert s.count(a) == 1, 'chat-ui anchor'
    s = s.replace(a, a + js, 1)
open(p, 'w', encoding='utf-8').write(s); print('chat.html patched')
P
PY=$W/invoke/bin/python
export PLAYWRIGHT_BROWSERS_PATH="$W/tools/ms-playwright"
timeout 480 $PY -I - "$S/qa" <<'PY' 2>&1 | tail -c 300000
import sys, os, base64, time, urllib.request
from playwright.sync_api import sync_playwright
qa = sys.argv[1]; os.makedirs(qa, exist_ok=True)
url = "http://127.0.0.1:8091/web/chat.html"
def b64(name, path):
    data = base64.b64encode(open(path, "rb").read()).decode()
    print("B64_%s_BEGIN" % name)
    for i in range(0, len(data), 900): print(data[i:i+900])
    print("B64_%s_END" % name)
with sync_playwright() as p:
    br = p.chromium.launch(args=["--no-sandbox"])
    ctx = br.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
    pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)[:160]))
    pg.goto(url, wait_until="load", timeout=60000); pg.wait_for_timeout(2500)
    pg.screenshot(path=qa + "/t2_pc_empty.jpg", type="jpeg", quality=38)
    pg.fill("#input", "привет"); pg.wait_for_timeout(300); pg.keyboard.press("Enter")
    t0 = time.time()
    pg.wait_for_timeout(4000)
    while time.time() - t0 < 240:
        busy = pg.is_visible("#btnStop")
        n = pg.evaluate("document.querySelectorAll('#msgs > *').length")
        if not busy and n >= 2: break
        pg.wait_for_timeout(3000)
    print("waited %.0fs msgs=%d" % (time.time() - t0, pg.evaluate("document.querySelectorAll('#msgs > *').length")))
    classes = pg.evaluate("""() => { const s = new Set(); document.querySelectorAll('#msgs *').forEach(e => { if (e.className && typeof e.className === 'string') s.add(e.tagName + '.' + e.className.split(' ').join('.')); }); return Array.from(s).slice(0, 70); }""")
    print("CLASSES", " | ".join(classes))
    print("ROW_TOP_CLASSES", pg.evaluate("Array.from(document.querySelectorAll('#msgs > *')).map(e => e.className + ' @' + e.getBoundingClientRect().width.toFixed(0)).join(' ; ')")[:800])
    pg.wait_for_timeout(1200)
    pg.screenshot(path=qa + "/t2_pc.jpg", type="jpeg", quality=38)
    pg.set_viewport_size({"width": 390, "height": 844}); pg.wait_for_timeout(1200)
    pg.screenshot(path=qa + "/t2_mob.jpg", type="jpeg", quality=38)
    print("errors", len(errs), errs[:3])
    b64("pc", qa + "/t2_pc.jpg"); b64("mob", qa + "/t2_mob.jpg")
    br.close()
PY
echo "== done"
