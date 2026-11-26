echo "C300: ui_th_fix1"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/th_graphite
curl -fsSL --retry 5 $R/ensure.sh -o /tmp/th_ensure.sh && bash /tmp/th_ensure.sh force
S=/workspace/nox/web/site; cd $S
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
cat > /tmp/th_qa_f.py <<'PEOF'
import asyncio
from playwright.async_api import async_playwright
PAGES='index chat settings atlas training growth nexus memory organism assistant photo creative system music news cinema studio calendar finance live operators glance downloads'.split()
async def m():
  bad=0
  async with async_playwright() as p:
    b=await p.chromium.launch(args=['--use-gl=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist'])
    for pg in PAGES:
      c=await b.new_page(viewport={'width':1440,'height':900});errs=[];c.on('pageerror',lambda e:errs.append(str(e)[:90]))
      try:
        await c.goto('http://127.0.0.1:8091/web/%s.html'%pg,wait_until='domcontentloaded',timeout=25000);await c.wait_for_timeout(3500)
        r=await c.evaluate("[document.documentElement.getAttribute('data-nox-theme'),window.NOXiconSet||'',!!window.NOXgx]")
      except Exception as e: r=['EXC'];errs.append(str(e)[:60])
      ok=(r[0]=='graphite' or pg=='live') and not errs
      if not ok: bad+=1
      print('QA',pg,r,errs[:2],'OK' if ok else 'BAD',flush=True);await c.close()
    await b.close()
  print('QABAD',bad)
asyncio.run(m())
PEOF
timeout 280 $PY /tmp/th_qa_f.py
