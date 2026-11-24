#!/bin/bash
# b_voice_retest.sh: повторный тест голоса (10 фраз, в т.ч. «на 85%») + финальные скриншоты voice.html (ПК 1440x900, моб 390x844)
set -u
W=/workspace/nox
OUT=$W/web/site/qa/voice2
mkdir -p "$OUT"

echo "== tts2 health"
curl -s --max-time 10 http://127.0.0.1:8095/health; echo

echo "== test10 (повторный прогон)"
cd "$W/c300_voice/voice2" && timeout 900 python3 test10.py > "$OUT/test10_retest.log" 2>&1; echo "test10 rc=$?"
tail -c 5000 "$OUT/test10_retest.log"
echo "== проверка «на 85%»"
grep -n "85" "$OUT/test10_retest.log" | head -5

echo "== playwright screenshots"
export PLAYWRIGHT_BROWSERS_PATH="$W/tools/ms-playwright"
timeout 300 python3 - "$W/web/site/voice.html" "$OUT" <<'PY' 2>&1 | tail -20
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
ls -la "$OUT" | tail -20
