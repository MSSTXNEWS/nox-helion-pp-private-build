S=/workspace/nox/web/site
PY=/workspace/nox/venv/bin/python
$PY -I - <<'P'
import asyncio,json,base64,io
from collections import defaultdict
from playwright.async_api import async_playwright
nav=json.load(open('/workspace/nox/web/site/nav.json'))
pages=[i['file'][:-5] for g in nav['groups'] for i in g['items']]+['index']
JS="""()=>{const o=[];document.querySelectorAll('body *').forEach(e=>{const s=getComputedStyle(e);if((s.position==='fixed'||s.position==='sticky')&&e.offsetWidth>0&&e.offsetHeight>0){const r=e.getBoundingClientRect();o.push([e.tagName+'#'+e.id+'.'+(typeof e.className==='string'?e.className.split(' ').slice(0,3).join('.'):''),Math.round(r.left),Math.round(r.top),Math.round(r.width),Math.round(r.height),(e.innerText||e.getAttribute('aria-label')||e.title||'').slice(0,25).replace(/\\n/g,' ')])}});return o}"""
agg=defaultdict(list)
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch()
        for pg in pages:
            c=await b.new_page(viewport={"width":390,"height":844})
            try:
                await c.goto("http://127.0.0.1:8091/web/%s.html"%pg,wait_until="load",timeout=25000);await c.wait_for_timeout(1500)
                for r in await c.evaluate(JS): agg[r[0]].append((pg,r[1:]))
            except Exception as e: print("OUT: ERR",pg,str(e)[:80])
            if pg in("index",):
                await c.screenshot(path="/tmp/m_idx.jpg",type="jpeg",quality=40)
            await c.close()
        await b.close()
asyncio.run(main())
for k,v in sorted(agg.items(),key=lambda x:-len(x[1])):
    print("OUT:",len(v),k,v[0][1])
print("B64_idx_BEGIN");print(base64.b64encode(open('/tmp/m_idx.jpg','rb').read()).decode());print("B64_idx_END")
P
echo "OUT: modal selectors"; grep -ohE "(sl-dialog|sl-drawer|<dialog|class=\"[^\"]*(modal|overlay|popup|lightbox)[^\"]*\")" $S/*.html $S/nox-*.js | sort | uniq -c | sort -rn | head -25
echo "OUT: dock css"; grep -ohE "#nxdock[^{]*\{[^}]{0,200}\}" $S/*.css | head -8
