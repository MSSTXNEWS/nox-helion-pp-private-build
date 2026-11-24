# A: пересборка hud.js (createFrame отдельно от classList, лог ошибок) + проверка .nox-hud
export PATH=/workspace/nox/tools/node/bin:$PATH
S=/workspace/nox/web/site; B=/workspace/nox/build_a; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/a_src
mkdir -p $B/src $S/vendor/nox-fx
curl -fsSL "$R/hud.js?$(date +%s)" -o $B/src/hud.js || echo FAIL hud.js
cd $B && node_modules/.bin/esbuild --bundle --minify --format=esm --log-level=warning --define:process.env.NODE_ENV=\"production\" src/hud.js --outfile=$S/vendor/nox-fx/hud.js 2>&1 | tail -5
ls -la $S/vendor/nox-fx/hud.js
grep -c "nox-hud" $S/vendor/nox-fx/hud.js
python3 - <<'P'
import asyncio
async def main():
    try:
        from playwright.async_api import async_playwright
    except Exception as e:
        print("NO_PLAYWRIGHT", e); return
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for w,h,tag in ((1440,900,"pc"),(390,844,"mob")):
            pg = await b.new_page(viewport={"width":w,"height":h})
            logs=[]
            pg.on("console", lambda m: logs.append(m.type+": "+m.text) if m.type in ("warning","error") else None)
            await pg.goto("http://127.0.0.1:8091/web/consciousness.html", wait_until="networkidle")
            await pg.wait_for_timeout(5000)
            n = await pg.evaluate("document.querySelectorAll('.nox-hud').length")
            print("HUD", tag, "nox-hud count", n)
            for l in logs[:8]: print("LOG", l[:200])
            await pg.close()
        await b.close()
asyncio.run(main())
P
