import asyncio,json,base64,subprocess,sys
from playwright.async_api import async_playwright
CSS=open('/tmp/fix5.css').read()
async def m():
    async with async_playwright() as p:
        b=await p.chromium.launch(); c=await b.new_context(viewport={'width':int(sys.argv[1]),'height':int(sys.argv[2])}); await c.add_init_script("localStorage.setItem('nox.demo.off','1');window.__np=[];new MutationObserver(()=>{const n=document.querySelector('.nox-first');if(n){const t=(n.parentElement.id||n.parentElement.className.toString().slice(0,12));if(window.__np[window.__np.length-1]!==t)window.__np.push(t)}}).observe(document,{childList:true,subtree:true});"); pg=await c.new_page()
        await pg.goto('http://127.0.0.1:8091/web/chat.html',wait_until='domcontentloaded'); await pg.wait_for_timeout(9000)
        if len(sys.argv)>3: await pg.add_style_tag(content=CSS); await pg.wait_for_timeout(1500)
        print(await pg.evaluate("""(()=>{const h=document.querySelector('.tg-head'),s=document.querySelector('#stage');return 'head h='+(h.getBoundingClientRect().height|0)+' rows='+getComputedStyle(s).gridTemplateRows+' nox-first parents='+JSON.stringify(window.__np)+' form h='+(document.querySelector('#form').getBoundingClientRect().height|0)})()"""))
        await pg.screenshot(path='/tmp/q3.png'); await b.close()
    subprocess.run(['ffmpeg','-loglevel','error','-y','-i','/tmp/q3.png','-vf','scale=1000:-1','-q:v','8','/tmp/q3.jpg'])
    print('B64BEGIN'); b64=base64.b64encode(open('/tmp/q3.jpg','rb').read()).decode()
    for i in range(0,len(b64),180): print(b64[i:i+180])
    print('B64END')
asyncio.run(m())
