import asyncio
from playwright.async_api import async_playwright
async def touch(cdp,pts):
    x,y=pts[0]
    await cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':x,'y':y}]})
    for x,y in pts[1:]:
        await cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':x,'y':y}]});await asyncio.sleep(0.03)
    await cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch()
        ctx=await b.new_context(viewport={'width':390,'height':844},has_touch=True,is_mobile=True)
        pg=await ctx.new_page();reqs=[];pg.on('request',lambda r:reqs.append(r.method+' '+r.url[-50:]) if r.method=='POST' else None)
        errs=[];pg.on('pageerror',lambda e:errs.append(str(e)[:80]))
        await pg.goto('http://127.0.0.1:8091/web/chat.html',wait_until='load');await pg.wait_for_timeout(4000)
        inp=await pg.evaluate("(()=>{const t=document.querySelector('#form textarea,#form input[type=text],#form [contenteditable]');return t?t.tagName+'#'+t.id:'none'})()")
        print('OUT: input',inp,'tabs',await pg.evaluate("[...document.querySelectorAll('#nox-m-tab a,#nox-m-tab button')].map(e=>e.innerText.trim())"))
        async def val(): return await pg.evaluate("(()=>{const t=document.querySelector('#form textarea,#form input[type=text]');return t?t.value:''})()")
        # Команды
        await pg.click('a[href="#cmd"]');await pg.wait_for_timeout(700)
        items=await pg.evaluate("[...document.querySelectorAll('.nox-m-sheet button')].map(b=>b.innerText.trim())")
        print('OUT: cmd items',items)
        before=await val()
        tag=[i for i in items if i.startswith('/')][:1]
        if tag:
            await pg.click('.nox-m-sheet button:has-text("%s")'%tag[0]);await pg.wait_for_timeout(900)
            print('OUT: cmd tag',tag,'input before',repr(before),'after',repr(await val()),'sheetopen',await pg.evaluate("!!document.querySelector('.nox-m-sheet.open')"))
        await pg.click('a[href="#cmd"]');await pg.wait_for_timeout(600)
        mode=[i for i in items if i.startswith('Режим')][:1]
        if mode:
            st0=await pg.evaluate("document.querySelector('.lv-dd sl-button').innerText+'|'+[...document.querySelectorAll('.lv-tag')].map(t=>t.getAttribute('variant')+t.className).join(',')")
            await pg.click('.nox-m-sheet button:has-text("%s")'%mode[0]);await pg.wait_for_timeout(900)
            st1=await pg.evaluate("document.querySelector('.lv-dd sl-button').innerText+'|'+[...document.querySelectorAll('.lv-tag')].map(t=>t.getAttribute('variant')+t.className).join(',')")
            print('OUT: cmd mode',mode,'state changed',st0!=st1,'|',st1[:80],'input',repr(await val()))
        # Заготовки
        await pg.click('a[href="#tpl"]');await pg.wait_for_timeout(700)
        it2=await pg.evaluate("[...document.querySelectorAll('.nox-m-sheet button')].map(b=>b.innerText.trim())")
        print('OUT: tpl items',it2)
        if it2:
            b0=await val();n0=len(reqs)
            await pg.click('.nox-m-sheet button >> nth=0');await pg.wait_for_timeout(1500)
            print('OUT: tpl click',it2[0],'input',repr(b0),'->',repr((await val())[:40]),'posts',reqs[n0:][:3],'msgs',await pg.evaluate("document.querySelectorAll('#msgs > *').length"))
        # свайп назад
        await pg.goto('http://127.0.0.1:8091/web/news.html',wait_until='load');await pg.wait_for_timeout(2500)
        await pg.goto('http://127.0.0.1:8091/web/settings.html',wait_until='load');await pg.wait_for_timeout(2500)
        cdp=await ctx.new_cdp_session(pg)
        await touch(cdp,[(4,400),(40,402),(90,404),(150,405),(200,405)]);await pg.wait_for_timeout(2500)
        print('OUT: swipe-back url',pg.url[-20:])
        # PTR
        await pg.goto('http://127.0.0.1:8091/web/news.html',wait_until='load');await pg.wait_for_timeout(3000)
        await pg.evaluate("window.__flag=1;window.scrollTo(0,0)")
        print('OUT: ptr lib',await pg.evaluate("typeof PullToRefresh"))
        await touch(cdp,[(200,120)]+[(200,120+i*25) for i in range(1,16)]);await pg.wait_for_timeout(3500)
        print('OUT: ptr reloaded',await pg.evaluate("window.__flag!==1"))
        print('OUT: errs',errs)
        await b.close()
asyncio.run(main())
