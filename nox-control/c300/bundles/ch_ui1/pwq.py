import asyncio,json
from playwright.async_api import async_playwright
async def m():
    async with async_playwright() as p:
        b=await p.chromium.launch(); c=await b.new_context(viewport={'width':2559,'height':950}); await c.add_init_script("localStorage.setItem('nox.demo.off','1')"); pg=await c.new_page()
        await pg.goto('http://127.0.0.1:8091/web/chat.html',wait_until='domcontentloaded'); await pg.wait_for_timeout(7000)
        print(await pg.evaluate("""(()=>{const o=[];for(const e of document.querySelectorAll('button,a,div,span')){if(e.textContent.trim()==='?'&&e.children.length<2){const r=e.getBoundingClientRect();o.push(e.tagName+'#'+e.id+'.'+e.className.toString().slice(0,40)+' pos:'+getComputedStyle(e).position+' '+[r.left|0,r.top|0,r.width|0,r.height|0])}}
        const nf=document.querySelector('.nox-first');o.push('nox-first '+(nf?nf.outerHTML.slice(0,300)+' pos:'+getComputedStyle(nf).position:'none'));o.push('theme '+document.documentElement.getAttribute('data-nox-theme')+' ls '+localStorage.getItem('nox.ui.theme'));
        const st=document.querySelector('#stage');o.push('rows '+getComputedStyle(st).gridTemplateRows+' / '+getComputedStyle(document.querySelector('.tg-head')).height);return o.join('\\n')})()"""))
        await b.close()
asyncio.run(m())
