echo "C300: u_idx2"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
cp index.html index.html.bak_u_$TS
python3 - <<'PYX'
f='index.html';s=open(f,encoding='utf-8').read()
tags=''
if 'nox-k8-ui.css' not in s: tags+='<link rel="stylesheet" href="./nox-k8-ui.css?v=k8b">'
for m in ('win','voice','meta','live'):
    if './nox-k8-%s.js'%m not in s: tags+='<script src="./nox-k8-%s.js?v=k8b" defer></script>'%m
i=s.rfind('</body>');s=s[:i]+tags+s[i:] if i>=0 else s+tags
open(f,'w',encoding='utf-8').write(s);print('added',tags.count('<'))
PYX
echo "U: k8 win/voice/meta/live подключены" >> qa/rework/index.fixed
timeout 200 $PY - <<'QAEOF' | tee /tmp/u_qa_idx.txt
import asyncio
from playwright.async_api import async_playwright
JS="""(async()=>{const o={};localStorage.removeItem('nox.k8.win.t');o.win=typeof K8win;o.live=typeof K8live;o.voice=typeof K8voice;o.meta=typeof K8meta;o.f1=await K8win.fire('тест');o.t=await K8live.tick();o.el=!!document.getElementById('k8-live');return JSON.stringify(o)})()"""
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    for w,h in((1440,900),(390,844)):
      pg=await b.new_page(viewport={'width':w,'height':h});errs=[];pg.on('pageerror',lambda e:errs.append(str(e)[:140]))
      try:
        await pg.goto('http://127.0.0.1:8091/web/index.html'+('?home=1' if w<500 else ''),wait_until='domcontentloaded',timeout=40000);await pg.wait_for_timeout(4000)
        r=await asyncio.wait_for(pg.evaluate(JS),40);print('QA',w,r,'errs',errs[:4])
      except Exception as e: print('QA EXC',w,str(e)[:200],errs[:3])
      await pg.close()
    await b.close()
asyncio.run(m())
QAEOF
if grep -q "EXC\|errs \['" /tmp/u_qa_idx.txt; then cp index.html.bak_u_$TS index.html && echo ROLLBACK; else echo "INDEX OK"; fi
echo "u_idx2 done"
