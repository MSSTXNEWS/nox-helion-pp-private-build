echo "C300: k7_probe_1"
S=/workspace/nox/web/site; cd $S
ls | grep -E "^nox-k[3-6]" | tr '\n' ' '; echo
ls vendor | tr '\n' ' '; echo
ls vendor/fuse.js vendor/embla-carousel vendor/auto-animate vendor/animate.css 2>&1 | head -20
head -c 700 data/news.json; echo; ls data | tr '\n' ' '; echo
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
timeout 170 $PY - <<'QAEOF'
import asyncio
from playwright.async_api import async_playwright
JS="""(()=>{const q=s=>[...document.querySelectorAll(s)];const o={};
o.ids=q('[id]').map(e=>e.tagName.toLowerCase()+'#'+e.id).slice(0,60).join(' ');
o.imgs=q('img,canvas,video').map(e=>e.tagName.toLowerCase()+'#'+e.id+'.'+String(e.className).slice(0,30)+' '+Math.round(e.getBoundingClientRect().width)+'x'+Math.round(e.getBoundingClientRect().height)).slice(0,12).join(' | ');
o.cls=[...new Set(q('body *').map(e=>String(e.className)).filter(c=>c&&!c.includes('[object')).flatMap(c=>c.split(' ')).filter(c=>c&&!c.startsWith('k4')&&!c.startsWith('k5')&&!c.startsWith('k6')))].slice(0,70).join(' ');
return JSON.stringify(o)})()"""
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch(args=[])
    for pg_ in ['index','photo','music','news','chat','soul','pdf','system','finance']:
      pg=await b.new_page(viewport={'width':1440,'height':900})
      try:
        await pg.goto('http://127.0.0.1:8091/web/%s.html'%pg_,wait_until='domcontentloaded',timeout=30000);await pg.wait_for_timeout(2500)
        print('PG',pg_,await asyncio.wait_for(pg.evaluate(JS),20))
      except Exception as e: print('PG',pg_,'EXC',str(e)[:200])
    await b.close()
asyncio.run(m())
QAEOF
echo "K7 probe1 done"
