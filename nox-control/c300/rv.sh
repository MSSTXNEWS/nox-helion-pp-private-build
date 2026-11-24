#!/bin/bash
S=/workspace/nox/web/site
python3 - <<'P'
p="/workspace/nox/web/site/nox-nav.js"; s=open(p).read()
s=s.replace("\n/* c300: вау-навигация (категории снизу, система сверху) */\nimport('./nox-dock-wow.js').catch((e) => console.warn('dock-wow:', e.message));\n","\n")
open(p,"w").write(s); print("dock hook removed:", "nox-dock-wow" not in s)
P
n=0; for f in $S/*.html; do grep -q 'nox-dock-wow.js' $f && { sed -i '/<script src="\.\/nox-dock-wow.js" defer><\/script>/d' $f; n=$((n+1)); }; done; echo "dock tag removed from $n pages"
cat > /tmp/shot4.py <<'P'
import asyncio, base64, textwrap
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--use-gl=swiftshader","--enable-unsafe-swiftshader","--ignore-gpu-blocklist"])
        pg=await b.new_page(viewport={"width":1700,"height":900}); errs=[]; pg.on("pageerror", lambda e: errs.append(str(e)[:150]))
        await pg.goto("http://127.0.0.1:8091/web/index.html"); await pg.wait_for_timeout(9000); await pg.keyboard.press("Escape"); await pg.wait_for_timeout(1500)
        img=await pg.screenshot(type="jpeg", quality=38)
        print("B64_idx_BEGIN"); print("\n".join(textwrap.wrap(base64.b64encode(img).decode(), 900))); print("B64_idx_END"); print("ERRS", errs[:3]); await b.close()
asyncio.run(main())
P
timeout 120 /workspace/nox/venv/bin/python /tmp/shot4.py 2>&1 | grep -v "^\s*$"
