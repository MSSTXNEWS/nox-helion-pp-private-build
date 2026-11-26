echo "C300: ui_dep9 (студия роли Писатель)"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python; export PATH=/workspace/nox/tools/node/bin:$PATH
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
for f in writer.html roles.json nox-studio-roles.js; do curl -fsSL --retry 5 --retry-delay 4 --retry-all-errors $R/ui_studio/$f -o /tmp/$f && [ -s /tmp/$f ] || { echo "FAIL $f"; exit 0; }; done
node --check /tmp/nox-studio-roles.js && $PY -c "import json;json.load(open('/tmp/roles.json'))" || { echo FAIL_SYNTAX; exit 0; }
cp nav.json nav.json.bak_ui9_$TS; [ -f writer.html ] && cp writer.html writer.html.bak_ui9_$TS
cp /tmp/writer.html /tmp/nox-studio-roles.js .; cp /tmp/roles.json roles.json; mkdir -p /workspace/nox/state; [ -f /workspace/nox/state/roles.json ] && cp /workspace/nox/state/roles.json /workspace/nox/state/roles.json.bak_ui9_$TS; cp /tmp/roles.json /workspace/nox/state/roles.json
$PY - <<'P'
import json
d=json.load(open('nav.json')); done=False
for g in d['groups']:
    for it in g['items']:
        if it.get('file')=='writer.html': done=True
if not done:
    for g in d['groups']:
        for i,it in enumerate(g['items']):
            if it.get('file')=='tools.html':
                g['items'].insert(i+1,{"file":"writer.html","name":"Писатель","title":"NOX HELION · ПИСАТЕЛЬ","icon":"pencil","desc":"Студия текстов: холст, инструменты, чат","soon":False}); done=True; break
        if done: break
    json.dump(d,open('nav.json','w'),ensure_ascii=False,indent=1); print('nav added')
else: print('nav already')
P
cat > /tmp/ui_w.py <<'PEOF'
import asyncio
from playwright.async_api import async_playwright
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    for w,h in((1440,900),(390,844)):
      c=await b.new_page(viewport={'width':w,'height':h});errs=[];c.on('pageerror',lambda e:errs.append(str(e)[:100]))
      await c.goto('http://127.0.0.1:8091/web/writer.html',wait_until='domcontentloaded');await c.wait_for_timeout(5000)
      r=await c.evaluate("""()=>({th:document.documentElement.getAttribute('data-nox-theme'),btn:document.querySelectorAll('#rs-tools button').length,cm:!!document.querySelector('.CodeMirror'),small:[...document.querySelectorAll('#rs-tools button,#rs-chat button')].filter(e=>e.offsetHeight&&e.offsetHeight<43.5).length,hs:document.documentElement.scrollWidth<=innerWidth,role:window.NOXroleStudio&&NOXroleStudio.role&&NOXroleStudio.role.title})""")
      print('QAW',w,errs[:2],r,flush=True)
      if w==1440: await c.screenshot(path='/workspace/nox/agent/out/ui_writer_1440.jpg',type='jpeg',quality=80)
      await c.close()
    await b.close()
asyncio.run(m())
PEOF
timeout 100 $PY /tmp/ui_w.py | tee /tmp/ui_w.out
if grep -E "^QAW" /tmp/ui_w.out | grep -qE "QAW [0-9]+ \['|'cm': False|'th': None"; then cp nav.json.bak_ui9_$TS nav.json; rm -f writer.html nox-studio-roles.js; [ -f writer.html.bak_ui9_$TS ] && cp writer.html.bak_ui9_$TS writer.html; echo ROLLBACK_WRITER; else echo QA_CLEAN; fi
echo "== th marker"; curl -fsSL --retry 5 $R/th_graphite/ensure.sh -o /tmp/th_ensure.sh && bash /tmp/th_ensure.sh
