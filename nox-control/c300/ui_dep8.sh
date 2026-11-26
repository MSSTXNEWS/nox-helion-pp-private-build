echo "C300: ui_dep8"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python; export PATH=/workspace/nox/tools/node/bin:$PATH
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
V=x5
curl -fsSL --retry 5 --retry-delay 4 --retry-all-errors $R/ui_ux/nox-u-ux.css -o /tmp/nox-u-ux.css && curl -fsSL --retry 5 --retry-delay 4 --retry-all-errors $R/ui_ux/nox-u-ux.js -o /tmp/nox-u-ux.js && node --check /tmp/nox-u-ux.js && [ -s /tmp/nox-u-ux.css ] || { echo FAIL; exit 0; }
cp /tmp/nox-u-ux.css nox-u-ux.css; cp /tmp/nox-u-ux.js nox-u-ux.js
PAGES=""; for p in index creative settings system memory map knowledge widgets projects music news cinema mail calendar tools studio photo voice training dispatcher downloads board atlas pdf integrations assistant; do [ -f $p.html ] && PAGES="$PAGES $p"; done; echo PAGES $PAGES
mkdir -p /tmp/uibak8_$TS; for p in $PAGES; do cp $p.html /tmp/uibak8_$TS/$p.html; done
cat > /tmp/ui_inj.py <<'P'
import sys,re
V=sys.argv[1]
for p in sys.argv[2:]:
    f=p+'.html'; s=open(f,encoding='utf-8').read()
    if 'nox-u-ux.css' not in s:
        i=s.rfind('</body>'); s=s[:i]+'<link rel="stylesheet" href="./nox-u-ux.css?v=%s"><script src="./nox-u-ux.js?v=%s" defer></script>'%(V,V)+s[i:]
    else: s=re.sub(r'nox-u-ux\.(css|js)\?v=\w+',lambda m:'nox-u-ux.%s?v=%s'%(m.group(1),V),s)
    open(f,'w',encoding='utf-8').write(s)
P
python3 /tmp/ui_inj.py $V $PAGES
cat > /tmp/ui_qa8.py <<'PEOF'
import asyncio,sys,json
from playwright.async_api import async_playwright
async def one(b,pg):
  c=await b.new_page(viewport={'width':1440,'height':900});errs=[];c.on('pageerror',lambda e:errs.append(str(e)[:90]))
  try:
    await c.goto('http://127.0.0.1:8091/web/'+pg+('.html?home=1' if pg=='index' else '.html'),wait_until='domcontentloaded',timeout=25000);await c.wait_for_timeout(3000)
    r=await c.evaluate("""()=>{const o=[];for(const e of document.querySelectorAll('.tb-t,.tb-i,#nxdock a,#nxdock button')){const r=e.getBoundingClientRect();if(r.width&&r.height&&r.height<43.5)o.push(1)}return {th:document.documentElement.getAttribute('data-nox-theme'),small:o.length,hs:document.documentElement.scrollWidth<=innerWidth,cta:[...document.querySelectorAll('.u-cta')].map(e=>(e.textContent||'').trim().slice(0,18)),ux:!!window.NOXuux}}""")
  except Exception as e: r={'th':'EXC'};errs.append(str(e)[:60])
  await c.close(); return errs,r
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    for pg in sys.argv[1:]:
      errs,r=await one(b,pg); print('QA',pg,json.dumps({'e':errs[:2],**r},ensure_ascii=False),flush=True)
    await b.close()
asyncio.run(m())
PEOF
echo "== QA1"; timeout 240 $PY /tmp/ui_qa8.py $PAGES | tee /tmp/ui_qa8.out
BAD=$(grep "^QA" /tmp/ui_qa8.out | grep -E '"e": \["' | awk '{print $2}')
for p in $BAD; do cp $p.html /tmp/uibak8_$TS/$p.inj.html; cp /tmp/uibak8_$TS/$p.html $p.html; done
if [ -n "$BAD" ]; then echo "== recheck without injection: $BAD"; timeout 100 $PY /tmp/ui_qa8.py $BAD | tee /tmp/ui_qa8b.out
  for p in $BAD; do if grep "^QA $p " /tmp/ui_qa8b.out | grep -qE '"e": \["'; then echo "PREEXISTING_ERR $p -> оставляю с nox-u-ux"; cp /tmp/uibak8_$TS/$p.inj.html $p.html; else echo "ROLLBACK_PAGE $p (ошибка из-за nox-u-ux)"; fi; done; fi
echo "== theme check"; grep "^QA" /tmp/ui_qa8.out | grep -vE '"th": "graphite"' | cut -c1-80 && echo "THEME_MISSING_ABOVE" || echo "THEME_OK_ALL"
echo "== headers (SW/cache)"; for u in web/index.html "web/nox-u-ux.css?v=$V" "web/nox-u-ux.js?v=$V"; do curl -sI http://127.0.0.1:8091/$u | grep -iE "HTTP|cache-control|etag|last-modified" | tr '\n' ' '; echo; done
echo "== th marker"; curl -fsSL --retry 5 $R/th_graphite/ensure.sh -o /tmp/th_ensure.sh && bash /tmp/th_ensure.sh
