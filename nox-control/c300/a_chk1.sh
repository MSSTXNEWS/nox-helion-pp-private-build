cat > /tmp/chk.py <<'P'
import asyncio
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(args=["--use-gl=swiftshader","--enable-webgl","--ignore-gpu-blocklist"])
        for pg in ["chat","consciousness","organism","soul","growth","selffeel","training","index"]:
            c=await b.new_page(viewport={"width":1440,"height":900}); errs=[]
            c.on("pageerror",lambda e:errs.append("PE "+str(e)[:140])); c.on("response",lambda r:errs.append("HTTP%d %s"%(r.status,r.url[-70:])) if r.status>=400 else None)
            await c.goto("http://127.0.0.1:8091/web/%s.html"%pg,wait_until="load",timeout=30000); await c.wait_for_timeout(6000)
            n=await c.evaluate("()=>[document.querySelectorAll('.nbx').length,document.querySelectorAll('.nox-hud').length,!!document.querySelector('#nox-fx-ash canvas'),!!document.querySelector('#nuiFlow'),document.querySelectorAll('.nbx canvas').length]")
            print(pg,n,errs[:5])
            if pg=="chat":
                await c.fill("#input","Привет, ответь одним предложением."); await c.click("#btnSend",force=True)
                for i in range(40):
                    await c.wait_for_timeout(2000)
                    if not await c.evaluate("()=>document.body.classList.contains('nox-busy')") and i>1: break
                print("chat reply:",(await c.evaluate("()=>[...document.querySelectorAll('#msgs .m.a .txt')].pop()?.innerText||''"))[:120],"| nui:",await c.evaluate("()=>document.querySelectorAll('.nui-x .nui-reason').length"))
                await c.click("#nuiFlow",force=True); await c.wait_for_timeout(2500); print("flow nodes",await c.evaluate("()=>document.querySelectorAll('.react-flow__node').length"))
            await c.close()
        await b.close()
asyncio.run(main())
P
timeout 250 /workspace/nox/venv/bin/python /tmp/chk.py 2>&1 | tail -20
