cd /workspace/nox/web/site; grep -c "innerWidth >= 1280" nox-chat-tg.js; grep -o "nox-chat-tg.js?v=[0-9]*" chat.html
cd /tmp; cat > /tmp/dg3.py <<'P'
import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch()
        pg=await b.new_page(viewport={'width':1440,'height':900}); await pg.goto('http://127.0.0.1:8091/web/chat.html'); await pg.wait_for_timeout(6000)
        print(await pg.evaluate("""()=>{const e=document.querySelector('.cx-right');const b=e.getBoundingClientRect();return [document.body.className,Math.round(b.x),Math.round(b.y),Math.round(b.width),Math.round(b.height),getComputedStyle(e).visibility,e.innerText.slice(0,200),innerWidth,localStorage.getItem('nox.tg.right')].join(' | ')}"""))
        await b.close()
asyncio.run(main())
P
/workspace/nox/venv/bin/python /tmp/dg3.py 2>&1 | tail -5
