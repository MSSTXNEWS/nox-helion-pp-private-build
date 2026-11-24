# A: найти URL с 400 на training и проверить кнопки chat (клик всех кнопок, без отправки)
PY=/workspace/nox/venv/bin/python
$PY -I - <<'P'
import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width":1440,"height":900})
        bad=[]
        pg.on("response", lambda r: bad.append((r.status, r.url[:160])) if r.status>=400 else None)
        await pg.goto("http://127.0.0.1:8091/web/training.html", wait_until="networkidle")
        await pg.wait_for_timeout(3000)
        print("TRAINING_BAD", bad[:6])
        await pg.close()
        pg = await b.new_page(viewport={"width":1440,"height":900})
        errs=[]; bad2=[]
        pg.on("pageerror", lambda e: errs.append(str(e)[:160]))
        pg.on("response", lambda r: bad2.append((r.status, r.url[:160])) if r.status>=400 else None)
        await pg.goto("http://127.0.0.1:8091/web/chat.html", wait_until="networkidle")
        await pg.wait_for_timeout(3000)
        n = await pg.locator("button:visible").count()
        dead=[]
        for i in range(min(n,40)):
            try:
                t = await pg.locator("button:visible").nth(i).inner_text(timeout=1000)
                dead.append(t.strip()[:20])
            except Exception: pass
        print("CHAT_VISIBLE_BUTTONS", n, dead[:40])
        print("CHAT_ERRS", errs[:3], "BAD", bad2[:4])
        await b.close()
asyncio.run(main())
P
