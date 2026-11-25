echo "C300: k7_probe_2"
S=/workspace/nox/web/site; cd $S
grep -c "nox-k7" index.html; grep -o "nox-k7-[a-z]*.js" index.html | tr '\n' ' '
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
timeout 150 $PY - <<'QAEOF'
import asyncio
from playwright.async_api import async_playwright
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch(args=[])
    pg=await b.new_page(viewport={'width':390,'height':844});errs=[];pg.on('pageerror',lambda e:errs.append(str(e)[:140]))
    await pg.goto('http://127.0.0.1:8091/web/index.html',wait_until='domcontentloaded',timeout=40000)
    for t in (3,8,20):
      await pg.wait_for_timeout(t*1000 if t==3 else 6000)
      print('P',t,await pg.evaluate("JSON.stringify({u:location.href,k:[typeof K4,typeof K7cards,typeof K7find,typeof K7mesh],s:[...document.scripts].map(s=>s.src.split('/').pop()).filter(x=>/k7|k4-core/.test(x))})"),errs[:3])
    await b.close()
asyncio.run(m())
QAEOF
echo "K7 probe2 done"
