# A: пересборка hud.js (svg для createFrame) + проверка .nox-hud и скрины всех моих страниц одним прогоном
export PATH=/workspace/nox/tools/node/bin:$PATH
S=/workspace/nox/web/site; B=/workspace/nox/build_a; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/a_src
mkdir -p $B/src $S/vendor/nox-fx $S/qa/rework/a_shots
curl -fsSL "$R/hud.js?$(date +%s)" -o $B/src/hud.js || echo FAIL hud.js
cd $B && node_modules/.bin/esbuild --bundle --minify --format=esm --log-level=warning --define:process.env.NODE_ENV=\"production\" src/hud.js --outfile=$S/vendor/nox-fx/hud.js 2>&1 | tail -5
ls -la $S/vendor/nox-fx/hud.js
PY=/workspace/nox/venv/bin/python
$PY -I - <<'P'
import asyncio
from playwright.async_api import async_playwright
PAGES=["chat","consciousness","organism","soul","growth","selffeel","training"]
OUT="/workspace/nox/web/site/qa/rework/a_shots"
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for pgname in PAGES:
            for w,h,tag in ((1440,900,"pc"),(390,844,"mob")):
                pg = await b.new_page(viewport={"width":w,"height":h})
                errs=[]
                pg.on("console", lambda m: errs.append(m.type+": "+m.text[:160]) if m.type=="error" else None)
                pg.on("pageerror", lambda e: errs.append("pageerror: "+str(e)[:160]))
                try:
                    await pg.goto("http://127.0.0.1:8091/web/%s.html" % pgname, wait_until="networkidle", timeout=30000)
                    await pg.wait_for_timeout(3000)
                    n = await pg.evaluate("document.querySelectorAll('.nox-hud').length")
                    nb = await pg.evaluate("document.querySelectorAll('button').length")
                    await pg.screenshot(path="%s/%s_%s.png" % (OUT,pgname,tag))
                    print("PAGE", pgname, tag, "nox-hud", n, "buttons", nb, "errors", len(errs))
                    for e in errs[:3]: print("  ERR", e)
                except Exception as ex:
                    print("PAGE", pgname, tag, "FAIL", str(ex)[:160])
                await pg.close()
        await b.close()
asyncio.run(main())
P
