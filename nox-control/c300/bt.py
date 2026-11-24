import asyncio, json, sys
from playwright.async_api import async_playwright
IDS = ["code","console","board","notes","table","excel","word","pdf","ocr","upload","photo","gantt","mindmap","slides","map3d","globe","synth","visual","voice","sync"]
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--use-gl=swiftshader","--enable-unsafe-swiftshader","--ignore-gpu-blocklist","--autoplay-policy=no-user-gesture-required"])
        res = {}
        for i in IDS:
            pg = await b.new_page(viewport={"width":1400,"height":900}); errs=[]
            pg.on("pageerror", lambda e, errs=errs: errs.append("JS: "+str(e)[:160]))
            pg.on("console", lambda m, errs=errs: errs.append("console: "+m.text[:160]) if m.type=="error" else None)
            pg.on("requestfailed", lambda r, errs=errs: errs.append("404/fail: "+r.url[-90:]) if "nox-x" in r.url or "nox-tools" in r.url else None)
            await pg.goto("http://127.0.0.1:8091/web/tools.html#"+i, wait_until="load"); await pg.wait_for_timeout(6000)
            body = await pg.inner_text("#stBody") if await pg.query_selector("#stBody") else ""
            failed = "не открылся" in body
            kids = await pg.evaluate("document.querySelector('#stBody') ? document.querySelector('#stBody').querySelectorAll('*').length : 0")
            res[i] = {"ok": (not failed) and kids > 2, "nodes": kids, "errs": [e for e in errs if "favicon" not in e and "tile.openstreetmap" not in e][:3], "msg": body[:120] if failed else ""}
            await pg.close()
        g = await b.new_page(); await g.goto("http://127.0.0.1:8091/web/tools.html"); await g.wait_for_timeout(2500)
        print("tiles:", await g.evaluate("document.querySelectorAll('.nt-tile').length"))
        await b.close()
    for k,v in res.items(): print(("OK  " if v["ok"] else "BAD "), k, v["nodes"], v["msg"], " | ".join(v["errs"]))
asyncio.run(main())
