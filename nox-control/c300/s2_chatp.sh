#!/bin/bash
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright
PY=/workspace/nox/venv/bin/python
cat > /tmp/cp.py <<'P'
import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page()
        await pg.goto("http://127.0.0.1:8091/web/board.html"); await pg.wait_for_timeout(3000)
        r=await pg.evaluate("""async()=>{const t0=Date.now();const q='Разложи идеи на доске. Верни ТОЛЬКО JSON без пояснений: {"nodes":[{"id":1,"text":"короткая формулировка","group":"группа"}],"links":[[1,2]]}. До 12 узлов, группы 2-4. Идеи: запуск продукта: маркетинг, разработка, поддержка, финансы, юридические вопросы';
        const ac=new AbortController();setTimeout(()=>ac.abort(),200000);let out='',n=0;
        try{const r=await fetch('/api/chat',{method:'POST',signal:ac.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({stream:true,nox_mode:'fast',messages:[{role:'user',content:q}],message:{role:'user',content:q}})});
        const rd=r.body.getReader(),dc=new TextDecoder();while(true){const x=await rd.read();if(x.done)break;n++;out+=dc.decode(x.value)}}catch(e){out+='ERR '+e}
        return [Math.round((Date.now()-t0)/1000),n,out.slice(0,1500)]}""")
        print(r)
        await b.close()
asyncio.run(main())
P
$PY /tmp/cp.py 2>&1 | tail -20
