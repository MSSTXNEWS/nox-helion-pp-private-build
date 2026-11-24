#!/bin/bash
# b_voice_shot.sh: финальные скриншоты voice.html (ПК 1440x900, моб 390x844) + код _safe_accent/prep для разбора «+яйца»
set -u
W=/workspace/nox
OUT=$W/web/site/qa/voice2
mkdir -p "$OUT"
echo "== code: prep/_safe_accent"
sed -n 49,90p $W/c300_voice/voice2/tts2_server.py
echo "== playwright screenshots"
PY=$W/invoke/bin/python
export PLAYWRIGHT_BROWSERS_PATH="$W/tools/ms-playwright"
timeout 300 $PY - "$W/web/site/voice.html" "$OUT" <<'PY' 2>&1 | tail -20
import sys
from playwright.sync_api import sync_playwright
src, out = sys.argv[1], sys.argv[2]
with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox"])
    for name, w, h, mob in (("voice_final_pc", 1440, 900, False), ("voice_final_mob", 390, 844, True)):
        ctx = b.new_context(viewport={"width": w, "height": h}, is_mobile=mob, device_scale_factor=1)
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
        pg.goto("file://" + src, wait_until="load", timeout=60000)
        pg.wait_for_timeout(1500)
        pg.screenshot(path=f"{out}/{name}.png", full_page=True)
        print(name, "saved; page errors:", len(errs), errs[:3])
        ctx.close()
    b.close()
PY
ls "$OUT" | grep -i final
