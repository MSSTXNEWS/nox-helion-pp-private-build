echo "C300: th_chk6b (серверные снимки th5, проверка glance/downloads/live/operators)"
S=/workspace/nox/web/site; cd $S
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
cat > /tmp/th_chk6.py <<'PEOF'
import asyncio
from playwright.async_api import async_playwright
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    for pg in ('glance','downloads','live','operators','growth'):
      c=await b.new_page(viewport={'width':1440,'height':900});errs=[];fails=[]
      c.on('pageerror',lambda e:errs.append(str(e)[:100]));c.on('response',lambda r:fails.append('%d %s'%(r.status,r.url[-70:])) if r.status>=400 else None)
      await c.goto('http://127.0.0.1:8091/web/%s.html'%pg,wait_until='domcontentloaded',timeout=25000);await c.wait_for_timeout(5000)
      info=await c.evaluate("""()=>[document.documentElement.getAttribute('data-nox-theme'),[...document.querySelectorAll('iframe')].map(f=>{let t='';try{t=f.contentDocument.body.innerText.slice(0,60)}catch(e){t='xorigin'}return [f.getAttribute('src'),f.getBoundingClientRect().width|0,t]})]""")
      print('CHK',pg,info,errs[:2],fails[:4],flush=True)
      await c.screenshot(path='/workspace/nox/agent/out/th6_%s_1440.jpg'%pg,type='jpeg',quality=60);await c.close()
    await b.close()
asyncio.run(m())
PEOF
timeout 120 $PY /tmp/th_chk6.py
cd /workspace/nox/agent/out
$PY - <<'PEOF'
from PIL import Image,ImageDraw
import os
def sheet(names,out):
  W,H=640,400;c=Image.new('RGB',(W*3,H*2),(30,30,30));d=ImageDraw.Draw(c)
  for i,n in enumerate(names):
    f=n+'_1440.jpg'
    if os.path.exists(f): c.paste(Image.open(f).resize((W,H)),((i%3)*W,(i//3)*H));d.text(((i%3)*W+6,(i//3)*H+4),n,fill=(255,255,0))
  c.save(out,quality=45)
sheet(['th5_index','th5_chat','th5_atlas','th5_growth','th5_nexus','th5_organism'],'/tmp/th_sheetA.jpg')
sheet(['th5_assistant','th6_glance','th6_downloads','th6_live','th6_operators','th6_growth'],'/tmp/th_sheetB.jpg')
PEOF
ls -la /tmp/th_sheetA.jpg /tmp/th_sheetB.jpg
for n in A B; do echo "B64_sheet${n}_BEGIN"; base64 /tmp/th_sheet$n.jpg; echo "B64_sheet${n}_END"; done
echo done
