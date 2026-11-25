echo "C300: u_dep_ux2"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python; export PATH=/workspace/nox/tools/node/bin:$PATH
curl -fsSL --retry 5 --retry-delay 4 --retry-all-errors https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/u_a11y/nox-u-a11y.js -o /tmp/nox-u-a11y.js && node --check /tmp/nox-u-a11y.js && cp /tmp/nox-u-a11y.js nox-u-a11y.js && echo copied || { echo FAIL; exit 0; }
cp nox-k8-ui.css nox-k8-ui.css.bak_u3_$TS
for p in creative index settings; do cp $p.html $p.html.bak_u3_$TS; done
python3 - <<'PYX'
for f in ('creative.html','index.html','settings.html'):
    s=open(f,encoding='utf-8').read()
    if './nox-u-a11y.js' not in s:
        i=s.rfind('</body>');s=s[:i]+'<script src="./nox-u-a11y.js?v=u1" defer></script>'+s[i:];open(f,'w',encoding='utf-8').write(s);print('added',f)
PYX
grep -q U_LIVE44 nox-k8-ui.css || printf '\n/* U_LIVE44 */\n@media (max-width:768px){#k8-live{min-height:44px;font-size:14px}}\n' >> nox-k8-ui.css
sed -i -E 's#nox-k8-ui\.css\?v=[A-Za-z0-9_]+#nox-k8-ui.css?v=u3#' index.html creative.html settings.html
echo "== cal/events"
echo "GET /cal/events $(curl -s -m 5 -o /tmp/u_ce.txt -w '%{http_code}' localhost:8091/cal/events) $(head -c 150 /tmp/u_ce.txt)"
grep -n "cal/events\|events.json\|CAL" /workspace/nox/web/pkg/server/nox_extra.py | head -8 | cut -c1-180
cat > /tmp/u_ux.py <<'PEOF'
import asyncio
from playwright.async_api import async_playwright
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    for pg,w,h in (('creative',1440,900),('creative',390,844),('index',1440,900),('settings',1440,900)):
      c=await b.new_page(viewport={'width':w,'height':h});errs=[];bad=[]
      c.on('pageerror',lambda e:errs.append(str(e)[:100]));c.on('response',lambda r:bad.append(str(r.status)+' '+r.url[-40:]) if r.status>=400 and '/img/' not in r.url else None)
      await c.goto('http://127.0.0.1:8091/web/%s.html'%pg+('?home=1' if w<500 else ''),wait_until='domcontentloaded');await c.wait_for_timeout(6000)
      r=await c.evaluate("[document.querySelectorAll('sl-icon-button:not([label]),sl-icon-button[label=\"\"]').length,document.querySelectorAll('h1').length,(()=>{const e=document.getElementById('k8-live');return e?Math.round(e.getBoundingClientRect().height):null})()]")
      print('QA',pg,w,'nolabel/h1/live-h',r,errs[:2],'http>=400',bad[:3],flush=True);await c.close()
    await b.close()
asyncio.run(m())
PEOF
timeout 100 $PY /tmp/u_ux.py | tee /tmp/u_ux.out
grep -E "^QA" /tmp/u_ux.out | grep -q "Unexpected\|Error" && { for p in creative index settings; do cp $p.html.bak_u3_$TS $p.html; done; echo ROLLBACK; } || echo QA_CLEAN
echo "== audit progress"; cat /workspace/nox/agent/out/u_qab_prog.txt 2>/dev/null; pgrep -af qa_audit | cut -c1-90
echo done
