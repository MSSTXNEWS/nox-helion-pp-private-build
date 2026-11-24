# A: проверка .nox-hud и ошибок консоли (поиск python с playwright)
S=/workspace/nox/web/site
PY=""
for c in /workspace/nox/venv/bin/python python3 /usr/bin/python3; do
  if $c -c "import playwright" 2>/dev/null; then PY=$c; break; fi
done
if [ -z "$PY" ]; then echo "NO_PY_PLAYWRIGHT"; ls /workspace/nox/venv/bin 2>/dev/null | head -20; find / -maxdepth 6 -type d -name playwright 2>/dev/null | head -5; exit 0; fi
echo "PY=$PY"
ls -la $S/vendor/nox-fx/hud.js
$PY -I - <<'P'
import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for w,h,tag in ((1440,900,"pc"),(390,844,"mob")):
            pg = await b.new_page(viewport={"width":w,"height":h})
            logs=[]
            pg.on("console", lambda m: logs.append(m.type+": "+m.text) if m.type in ("warning","error") else None)
            pg.on("pageerror", lambda e: logs.append("pageerror: "+str(e)))
            await pg.goto("http://127.0.0.1:8091/web/consciousness.html", wait_until="networkidle")
            await pg.wait_for_timeout(5000)
            n = await pg.evaluate("document.querySelectorAll('.nox-hud').length")
            print("HUD", tag, "nox-hud count", n)
            for l in logs[:8]: print("LOG", l[:300])
            await pg.close()
        await b.close()
asyncio.run(main())
P
