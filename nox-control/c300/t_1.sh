#!/bin/bash
# t_1.sh (исполнитель T): диагностика чата, без изменений на сервере.
# Печатает chat.html, список селекторов CSS, хвост nox-wow.js по чату и скриншоты ПК/моб (base64 JPEG).
set -u
W=/workspace/nox
S=$W/web/site
echo "== site chat files"
ls -la $S 2>&1 | grep -i -E "chat|nox-wow\.js|nox-theme" | head -30
echo "== vendor/nox-chat-ui"
ls -la $S/vendor/nox-chat-ui 2>&1 | head -20
echo "== chat.html"
cat $S/chat.html 2>&1 | head -c 30000
echo
echo "== nox-chat-x.css selectors"
wc -c $S/nox-chat-x.css $S/nox-chat-x.js 2>&1
grep -oE '[.#][a-zA-Z_][a-zA-Z0-9_-]*' $S/nox-chat-x.css 2>/dev/null | sort | uniq -c | sort -rn | head -150 | tr '\n' ' '
echo
echo "== nox-wow.js chat hooks"
grep -n -i "chat\|nuiFlow\|ptt\|hint\|enter" $S/nox-wow.js 2>/dev/null | cut -c1-160 | head -60
echo "== screenshots"
PY=$W/invoke/bin/python
export PLAYWRIGHT_BROWSERS_PATH="$W/tools/ms-playwright"
timeout 300 $PY -I - "$S" "$W/web/site/qa" <<'PY' 2>&1 | tail -c 300000
import sys, os, base64, urllib.request
from playwright.sync_api import sync_playwright
site, qa = sys.argv[1], sys.argv[2]
os.makedirs(qa, exist_ok=True)
url = None
for cand in ("http://127.0.0.1:8091/chat.html", "http://127.0.0.1:8091/web/chat.html"):
    try:
        if urllib.request.urlopen(cand, timeout=5).status == 200: url = cand; break
    except Exception as e: print("probe", cand, str(e)[:80])
if url is None: url = "file://" + site + "/chat.html"
print("URL", url)
with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox"])
    for name, w, h, mob in (("pc", 1440, 900, False), ("mob", 390, 844, True)):
        ctx = b.new_context(viewport={"width": w, "height": h}, is_mobile=mob, device_scale_factor=1)
        pg = ctx.new_page(); errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)[:160]))
        pg.goto(url, wait_until="load", timeout=60000); pg.wait_for_timeout(2500)
        fp = qa + "/t_" + name + ".jpg"
        pg.screenshot(path=fp, type="jpeg", quality=38)
        print("errors", name, len(errs), errs[:3])
        data = base64.b64encode(open(fp, "rb").read()).decode()
        print("B64_%s_BEGIN" % name)
        for i in range(0, len(data), 900): print(data[i:i+900])
        print("B64_%s_END" % name)
        ctx.close()
    b.close()
PY
echo "== done"
