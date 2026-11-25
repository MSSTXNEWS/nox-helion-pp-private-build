PY=/workspace/nox/venv/bin/python
$PY -I - <<'P'
import asyncio
from playwright.async_api import async_playwright
JS="""()=>{const o=[];const d=(e,n)=>{if(n>4)return;[...e.children].forEach(c=>{if(['SCRIPT','STYLE'].includes(c.tagName))return;const r=c.getBoundingClientRect();o.push(' '.repeat(n)+c.tagName+'#'+c.id+'.'+(typeof c.className==='string'?c.className.split(' ').slice(0,3).join('.'):'')+' '+Math.round(r.left)+','+Math.round(r.top)+' '+Math.round(r.width)+'x'+Math.round(r.height)+' '+(c.children.length?'':(c.innerText||'').slice(0,18).replace(/\\n/g,' ')));d(c,n+1)})};d(document.querySelector('#app'),0);return o.join('\\n')}"""
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch();c=await b.new_page(viewport={"width":390,"height":844})
        await c.goto("http://127.0.0.1:8091/web/chat.html",wait_until="load");await c.wait_for_timeout(3000)
        print("OUT:\n"+await c.evaluate(JS))
        await b.close()
asyncio.run(main())
P
