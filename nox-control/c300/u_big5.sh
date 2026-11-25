echo "C300: u_big5"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
echo "== 2 fix: fab выше пилюли навигации (десктоп)"
cp nox-unify.css nox-unify.css.bak_u_$TS
grep -q U_FABUP nox-unify.css || printf '\n/* U_FABUP: мини-чат NOX не перекрыт пилюлей навигации */\n@media (min-width:769px){body:has(#nxnavx) .nmc-fab{bottom:calc(var(--ds-dock-h,0px) + var(--ds-safe-b,0px) + 76px) !important}}\n' >> nox-unify.css
grep -c U_FABUP nox-unify.css
sed -i -E 's#nox-unify\.css\?v=[A-Za-z0-9_]+#nox-unify.css?v=u1#' *.html
echo "== 3 проверка клика и 4K"
cat > /tmp/u_v.py <<'PEOF'
import asyncio
from playwright.async_api import async_playwright
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    for pg in ('finance','mail','news','training','creative','settings','index'):
      c=await b.new_page(viewport={'width':1440,'height':900});errs=[];c.on('pageerror',lambda e:errs.append(str(e)[:80]))
      await c.goto('http://127.0.0.1:8091/web/%s.html'%pg,wait_until='domcontentloaded');await c.wait_for_timeout(3000)
      try:
        await c.click('.nmc-fab',timeout=2500);await c.wait_for_timeout(600);ok=await c.evaluate("!!document.querySelector('.nmc-fab.on')")
      except Exception as e: ok='ERR '+str(e)[:60]
      print('FAB',pg,ok,errs[:2],flush=True);await c.close()
    for w,h in((2560,1440),(3840,2160)):
      for pg in ('index','chat','creative','finance','settings','training'):
        c=await b.new_page(viewport={'width':w,'height':h});errs=[];c.on('pageerror',lambda e:errs.append(str(e)[:80]))
        try:
          await c.goto('http://127.0.0.1:8091/web/%s.html'%pg,wait_until='domcontentloaded',timeout=30000);await c.wait_for_timeout(2500)
          r=await c.evaluate("[document.documentElement.scrollWidth,innerWidth,Math.round(Math.min(...[...document.querySelectorAll('main,#page,.page')].map(x=>x.getBoundingClientRect().width||1e9)))]")
          print('4K',w,pg,r,'js',len(errs),errs[:1],flush=True)
        except Exception as e: print('4K EXC',w,pg,str(e)[:80],flush=True)
        await c.close()
    await b.close()
asyncio.run(m())
PEOF
timeout 200 $PY /tmp/u_v.py
echo "== 4 audit"; cut -c1-330 /tmp/u_aud.out | sed -n 17,100p
echo "u_big5 done"
