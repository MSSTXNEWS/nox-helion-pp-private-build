import asyncio,json,base64,subprocess
from playwright.async_api import async_playwright
async def m():
    async with async_playwright() as p:
        b=await p.chromium.launch(); c=await b.new_context(viewport={'width':2559,'height':950}); await c.add_init_script("localStorage.setItem('nox.demo.off','1')"); pg=await c.new_page()
        await pg.goto('http://127.0.0.1:8091/web/chat.html',wait_until='domcontentloaded'); await pg.wait_for_timeout(9000)
        print(await pg.evaluate("""(()=>{const h=document.querySelector('.tg-head'),s=document.querySelector('#stage');const cs=getComputedStyle(s),ch=getComputedStyle(h);const o=['tgs='+cs.getPropertyValue('--tgs')+' stage fs='+cs.fontSize+' zoom='+getComputedStyle(document.body).zoom+' head fs='+ch.fontSize+' minh='+ch.minHeight+' pad='+ch.padding+' h='+h.getBoundingClientRect().height,'body classes='+document.body.className,'tgs root='+getComputedStyle(document.documentElement).getPropertyValue('--tgs')];
        for(const e of h.querySelectorAll('*')){const r=e.getBoundingClientRect();if(r.height>70)o.push(e.tagName+'#'+e.id+'.'+e.className.toString().slice(0,30)+' h'+(r.height|0)+' fs'+getComputedStyle(e).fontSize)}
        o.push('stage kids: '+[...s.children].map(x=>(x.id||x.className.toString().slice(0,14))+':'+(x.getBoundingClientRect().height|0)).join(' '));return o.join('\\n')})()"""))
        await pg.screenshot(path='/tmp/q2.png'); await b.close()
    subprocess.run(['ffmpeg','-loglevel','error','-y','-i','/tmp/q2.png','-vf','scale=1100:-1','-q:v','8','/tmp/q2.jpg'])
    print('B64BEGIN'); b64=base64.b64encode(open('/tmp/q2.jpg','rb').read()).decode()
    for i in range(0,len(b64),180): print(b64[i:i+180])
    print('B64END')
asyncio.run(m())
