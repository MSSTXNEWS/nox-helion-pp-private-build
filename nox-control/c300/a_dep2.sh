# A: раскладка nox-fx/brain/feed с бэкапом, компиляция, перезапуск датчика, проверка live.json и скринов 1440/390/3840
S=/workspace/nox/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/a_src; T=$(date +%s)
mkdir -p /workspace/nox/tools $S/qa/rework/a_shots
for f in nox-fx.js nox-fx.css nox-brain-x.js nox-brain-x.css nox_a_feed.py; do curl -fsSL "$R/$f?$T" -o /tmp/a_$f || echo FAIL $f; done
for f in nox-fx.js nox-fx.css nox-brain-x.js nox-brain-x.css; do [ -f $S/$f ] && [ ! -f $S/$f.bak_a_2 ] && cp $S/$f $S/$f.bak_a_2; cp /tmp/a_$f $S/$f; done
[ -f /workspace/nox/tools/nox_a_feed.py ] && cp /workspace/nox/tools/nox_a_feed.py /workspace/nox/tools/nox_a_feed.py.bak_a_2
cp /tmp/a_nox_a_feed.py /workspace/nox/tools/nox_a_feed.py && python3 -I -m py_compile /workspace/nox/tools/nox_a_feed.py && echo COMPILE_OK
pkill -f nox_a_feed.py; sleep 1; nohup setsid python3 /workspace/nox/tools/nox_a_feed.py >/workspace/nox/tools/logs_a_feed.log 2>&1 &
sleep 40; ls -la $S/data/live.json 2>&1; head -c 400 $S/data/live.json 2>/dev/null; echo
/workspace/nox/venv/bin/python -I - <<'P'
import asyncio
from playwright.async_api import async_playwright
PAGES=["consciousness","organism","training"]
OUT="/workspace/nox/web/site/qa/rework/a_shots"
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch()
        for pgname in PAGES:
            for w,h,tag in ((1440,900,"pc"),(390,844,"mob"),(3840,2160,"4k")):
                pg=await b.new_page(viewport={"width":w,"height":h}); errs=[]
                pg.on("pageerror", lambda e: errs.append(str(e)[:140]))
                try:
                    await pg.goto("http://127.0.0.1:8091/web/%s.html"%pgname, wait_until="networkidle", timeout=30000)
                    await pg.wait_for_timeout(4000)
                    live=await pg.evaluate("document.querySelectorAll('#nbxLive .nbx-tbl tbody tr').length")
                    ov=await pg.evaluate("document.documentElement.scrollWidth>window.innerWidth")
                    await pg.screenshot(path="%s/%s_%s.png"%(OUT,pgname,tag))
                    print("PAGE",pgname,tag,"live_rows",live,"hscroll",ov,"errs",len(errs), errs[:2])
                except Exception as ex: print("PAGE",pgname,tag,"FAIL",str(ex)[:140])
                await pg.close()
        await b.close()
asyncio.run(main())
P
