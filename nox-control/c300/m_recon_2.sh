S=/workspace/nox/web/site
PY=/workspace/nox/venv/bin/python
$PY -I - <<'P'
import json
n=json.load(open('/workspace/nox/web/site/nav.json'))
for g in n['groups']:
    print("OUT: G",g['group'],[ (i['file'][:-5],i['name'],i.get('icon'),i.get('soon')) for i in g['items']])
print("OUT: keys",[k for k in n if k!='groups'])
P
echo "OUT: no-ds pages: $(grep -L 'nox-ds.js' $S/*.html | xargs -n1 basename | tr '\n' ' ')"
echo "OUT: dock.js head"; head -c 1500 $S/nox-dock.js; echo
echo "OUT: shell head"; ls $S/nox-shell.js $S/nox-nav.js; head -c 1500 $S/nox-shell.js; echo
echo "OUT: index script tags"; grep -oE "<script[^>]*src=[^>]*>|<link[^>]*stylesheet[^>]*>" $S/news.html | head -50
$PY -I - <<'P'
import asyncio
from playwright.async_api import async_playwright
JS="""()=>{const o=[];document.querySelectorAll('body *').forEach(e=>{const s=getComputedStyle(e);if(s.position==='fixed'&&e.offsetWidth>0){const r=e.getBoundingClientRect();o.push((e.tagName+'#'+e.id+'.'+(e.className&&e.className.baseVal===undefined?e.className:'')).slice(0,60)+' '+Math.round(r.left)+','+Math.round(r.top)+' '+Math.round(r.width)+'x'+Math.round(r.height))}});return o}"""
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch()
        for pg in ["news","chat","index","finance"]:
            c=await b.new_page(viewport={"width":390,"height":844})
            await c.goto("http://127.0.0.1:8091/web/%s.html"%pg,wait_until="load");await c.wait_for_timeout(2500)
            print("OUT: FIXED",pg,await c.evaluate(JS))
            print("OUT: sw",pg,await c.evaluate("document.documentElement.scrollWidth"))
        await b.close()
asyncio.run(main())
P
