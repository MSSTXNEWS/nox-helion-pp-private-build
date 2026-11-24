cd /workspace/nox/web/site
echo "== overlay src"; grep -l "Вернуть NOX\|Площадка" *.js *.html 2>/dev/null | head -20
grep -o '<script[^>]*src="[^"]*"' photo.html
echo "== rv state"; grep -c "nox-dock-wow" *.html | grep -v ":0" | head; grep -n "dock-wow" nox-nav.js
/workspace/nox/venv/bin/python - <<'P'
import asyncio,base64
from playwright.async_api import async_playwright
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch(args=["--use-gl=swiftshader","--enable-webgl"])
    pg=await b.new_page(viewport={"width":1280,"height":800})
    await pg.goto("http://127.0.0.1:8091/web/photo.html",wait_until="networkidle"); await pg.wait_for_timeout(5000)
    print("OVL",await pg.evaluate("""()=>[...document.querySelectorAll('body *')].filter(e=>/Площадка|Вернуть NOX/.test(e.textContent)&&e.children.length<3).slice(0,3).map(e=>e.tagName+'#'+e.id+'.'+e.className+' <'+(e.closest('[id]')||{}).id)"""))
    d=base64.b64encode(await pg.screenshot(type="jpeg",quality=30)).decode()
    print("B64_desk_BEGIN")
    for i in range(0,len(d),900): print(d[i:i+900])
    print("B64_desk_END")
    await b.close()
asyncio.run(m())
P
