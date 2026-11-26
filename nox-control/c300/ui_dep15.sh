echo "C300: ui_dep15 (5 миров из FASTWOW, как есть, оверлей)"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s); F=/workspace/nox/web/v29src/FASTWOW/site
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
for f in nox-cinematic-worlds.js nox-cinematic-worlds.css nox-world-themes.css; do [ -s $F/$f ] && cp -p $F/$f $S/$f || echo "FAIL $f"; done
PAGES=$(ls *.html | sed 's/\.html$//' | grep -vE '^(chat|chat-dc|book-reader|library|reader)$|\.main$' | tr '\n' ' ')
echo "PAGES $(echo $PAGES | wc -w)"
mkdir -p /tmp/uibak15_$TS; for p in $PAGES; do cp $p.html /tmp/uibak15_$TS/$p.html; done
cat > /tmp/ui_inj15.py <<'P'
import sys
V=sys.argv[1]
for p in sys.argv[2:]:
    f=p+'.html'; s=open(f,encoding='utf-8',errors='ignore').read()
    if 'data-nox-five-worlds' in s: continue
    i=s.rfind('</body>')
    if i<0: continue
    s=s[:i]+'<link rel="stylesheet" href="./nox-world-themes.css?v=%s"><link rel="stylesheet" href="./nox-cinematic-worlds.css?v=%s" data-nox-five-worlds="v3"><script defer src="./nox-cinematic-worlds.js?v=%s" data-nox-five-worlds="v3"></script>'%(V,V,V)+s[i:]
    open(f,'w',encoding='utf-8').write(s)
P
python3 /tmp/ui_inj15.py w1 $PAGES
cat > /tmp/ui_qa15.py <<'PEOF'
import asyncio,sys,json
from playwright.async_api import async_playwright
async def one(b,pg,world):
  c=await b.new_context(viewport={'width':1440,'height':900})
  if world: await c.add_init_script("localStorage.setItem('nox.cinematic.world.v3','%s')"%world)
  x=await c.new_page();errs=[];x.on('pageerror',lambda e:errs.append(str(e)[:90]))
  try:
    await x.goto('http://127.0.0.1:8091/web/'+pg+('.html?home=1' if pg=='index' else '.html'),wait_until='domcontentloaded',timeout=25000);await x.wait_for_timeout(2500)
    r=await x.evaluate("()=>({th:document.documentElement.getAttribute('data-nox-theme'),w:!!window.NOX_CINEMATIC_WORLDS,hs:document.documentElement.scrollWidth>innerWidth+1})")
  except Exception as e: r={'th':'EXC'};errs.append(str(e)[:60])
  await c.close(); return errs,r
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    for pg in sys.argv[2:]:
      errs,r=await one(b,pg,sys.argv[1] if sys.argv[1]!='-' else ''); print('QA',pg,json.dumps({'e':errs[:2],**r},ensure_ascii=False),flush=True)
    await b.close()
asyncio.run(m())
PEOF
echo "== QA default"; timeout 150 $PY /tmp/ui_qa15.py - $PAGES > /tmp/ui_qa15.out; grep -c '^QA' /tmp/ui_qa15.out; grep -E '"e": \["|"w": false|EXC' /tmp/ui_qa15.out | cut -c1-200 | head -20
echo "== QA forge on 8 pages"; timeout 60 $PY /tmp/ui_qa15.py forge index settings system calendar music memory photo creative | cut -c1-200
BAD=$(grep "^QA" /tmp/ui_qa15.out | grep -E '"e": \["' | awk '{print $2}')
if [ -n "$BAD" ]; then echo "== bad: $BAD"; for p in $BAD; do cp $p.html /tmp/uibak15_$TS/$p.inj.html; cp /tmp/uibak15_$TS/$p.html $p.html; done; timeout 60 $PY /tmp/ui_qa15.py - $BAD | cut -c1-200
 for p in $BAD; do if grep -q "^QA $p .*\"e\": \[\"" <(timeout 30 $PY /tmp/ui_qa15.py - $p); then echo "PREEXISTING_ERR $p"; else echo "ROLLBACK_PAGE $p (миры ломают)"; fi; done; fi
echo "== theme"; grep "^QA" /tmp/ui_qa15.out | grep -vc '"th": "graphite"'
curl -fsSL --retry 5 $R/th_graphite/ensure.sh -o /tmp/th_ensure.sh && bash /tmp/th_ensure.sh 2>&1 | tail -3
