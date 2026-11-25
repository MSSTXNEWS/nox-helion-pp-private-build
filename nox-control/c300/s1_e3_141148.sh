cat > /tmp/e2e.py <<'PYEOF'
import asyncio,sys,json
from playwright.async_api import async_playwright
pages=sys.argv[1].split(','); w=int(sys.argv[2]); h=int(sys.argv[3])
SKIP="header,footer,[id*=nav],[class*=nav],[class*=dock],[id*=dock],[class*=pult],[id*=pult],[class*=nmc],[id*=nxm],#nxmPill,[class*=minichat],.nai-dr,[class*=sun],[id*=sun]"
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=['--use-gl=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist'])
        for pg_name in pages:
            pg=await b.new_page(viewport={'width':w,'height':h}); reqs=[0]; errs=[]
            pg.on('request',lambda r:reqs.__setitem__(0,reqs[0]+1)); pg.on('pageerror',lambda e:errs.append(str(e)[:100]))
            url='http://localhost:8091/web/'+pg_name
            try: await pg.goto(url,wait_until='domcontentloaded',timeout=30000)
            except Exception as e: print(pg_name,'GOTO FAIL'); continue
            await pg.wait_for_timeout(7000)
            n=await pg.evaluate("""(skip)=>{window.__m=0;new MutationObserver(l=>{window.__m+=l.length}).observe(document.body,{subtree:true,childList:true,attributes:true,characterData:true});
              const els=[...document.querySelectorAll('button,sl-button,sl-icon-button,[role=tab],sl-switch,sl-select')].filter(e=>{const r=e.getBoundingClientRect();if(r.width<2||r.height<2||r.bottom<0||r.top>innerHeight)return false;if(e.closest(skip))return false;if(e.disabled||e.hasAttribute('disabled'))return false;return true});
              window.__els=els;els.forEach((e,i)=>e.dataset.s1i=i);return els.length}""",SKIP)
            dead=[];tot=min(n,24)
            for i in range(tot):
                try:
                    info=await pg.evaluate("(i)=>{const e=document.querySelector('[data-s1i=\"'+i+'\"]');if(!e)return null;return [e.tagName,(e.id||'')+'.'+(e.className+'').slice(0,30),(e.textContent||e.getAttribute('label')||e.getAttribute('title')||e.getAttribute('name')||'').trim().slice(0,24),e.tagName==='SL-SELECT'||e.tagName==='SL-SWITCH']}",i)
                    if not info or info[3]: continue
                    m0=await pg.evaluate("window.__m"); r0=reqs[0]; u0=pg.url
                    await pg.evaluate("(i)=>document.querySelector('[data-s1i=\"'+i+'\"]').click()",i); await pg.wait_for_timeout(500)
                    m1=await pg.evaluate("window.__m"); 
                    if pg.url!=u0:
                        await pg.goto(url,wait_until='domcontentloaded'); await pg.wait_for_timeout(3000); break
                    if m1==m0 and reqs[0]==r0: dead.append(info[1]+'|'+info[2])
                except Exception as e: dead.append('ERR '+str(e)[:40])
            print('E2E',pg_name,w,'checked',tot,'of',n,'dead',len(dead),dead,'errs',errs[:2])
            await pg.close()
        await b.close()
asyncio.run(main())
PYEOF
cd /tmp; /workspace/nox/venv/bin/python /tmp/e2e.py index.html,chat.html,voice.html 390 844 2>&1
