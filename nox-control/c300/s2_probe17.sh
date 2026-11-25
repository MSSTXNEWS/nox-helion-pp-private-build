#!/bin/bash
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright
PY=/workspace/nox/venv/bin/python
cat > /tmp/p17.py <<'P'
import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page()
        await pg.goto("http://127.0.0.1:8091/web/cinema.html"); await pg.wait_for_timeout(2500)
        print(await pg.evaluate("()=>Object.keys(NOX_vidstack).filter(k=>/Element|define|Layout|Player|Provider/i.test(k)).join(',')"))
        await b.close()
asyncio.run(main())
P
$PY /tmp/p17.py 2>&1 | tail -5
tail -15 /workspace/nox/svc/logs/whisperlive.log | cut -c1-200
ls /workspace/nox/svc/whisperlive; ls ~/.cache/huggingface/hub 2>/dev/null | head
