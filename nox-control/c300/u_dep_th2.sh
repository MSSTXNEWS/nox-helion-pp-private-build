echo "C300: u_dep_th2"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python; export PATH=/workspace/nox/tools/node/bin:$PATH
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
for f in u_creative/nox-u-creative.js u_board/nox-u-board.js u_hints/nox-u-hints.js u_index/nox-u-index.css; do b=$(basename $f); curl -fsSL --retry 5 --retry-delay 4 --retry-all-errors $R/$f -o /tmp/$b || { echo "FAIL $b"; exit 0; }; case $b in *.js) node --check /tmp/$b || { echo "SYNTAX $b"; exit 0; };; esac; [ -s /tmp/$b ] && cp $b $b.bak_u5_$TS 2>/dev/null; cp /tmp/$b $b; echo "deployed $b"; done
sed -i 's#nox-u-creative.js?v=u[0-9]#nox-u-creative.js?v=u5#' creative.html
sed -i 's#nox-u-hints.js?v=u[0-9]#nox-u-hints.js?v=u2#' settings.html
sed -i 's#nox-u-index.css?v=u[0-9]#nox-u-index.css?v=u3#' index.html
cat > /tmp/u_th.py <<'PEOF'
import asyncio
from playwright.async_api import async_playwright
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    for pg,w,h in(('creative',1440,900),('index',1440,900),('index',390,844),('settings',1440,900)):
      c=await b.new_page(viewport={'width':w,'height':h});errs=[];c.on('pageerror',lambda e:errs.append(str(e)[:100]))
      await c.goto('http://127.0.0.1:8091/web/%s.html'%pg+('?home=1' if w<500 else ''),wait_until='domcontentloaded');await c.wait_for_timeout(6000)
      extra=''
      if pg=='creative' and w==1440:
        await c.click('#u-hkb');await c.wait_for_timeout(1500);extra=await c.evaluate("(()=>{const d=document.getElementById('u-hk');return [d&&d.tagName,!!(d&&(d.open||d.hasAttribute('open')))]})()")
      if pg=='index' and w==1440: extra=await c.evaluate("[document.querySelectorAll('.hud-lbl').length,Math.max(0,...[...document.querySelectorAll('.hud-lbl')].map(e=>+getComputedStyle(e).opacity))]")
      print('QA',pg,w,extra,'ERRS',errs[:2],flush=True);await c.close()
    await b.close()
asyncio.run(m())
PEOF
timeout 100 $PY /tmp/u_th.py | tee /tmp/u_th.out
grep -E "^QA" /tmp/u_th.out | grep -q "ERRS \['" && { for f in nox-u-creative.js nox-u-board.js nox-u-hints.js nox-u-index.css; do cp $f.bak_u5_$TS $f 2>/dev/null; done; echo ROLLBACK; } || echo QA_CLEAN
echo "== queue audit rerun after settings (creative, index, settings)"
O=/workspace/nox/agent/out
cat > $O/u_audit6.sh <<'AEOF'
O=/workspace/nox/agent/out; cd /workspace/nox/web/site
while pgrep -f "qa_audit.py" >/dev/null; do sleep 20; done
rm -f $O/u_qac_*
for p in creative index settings; do /workspace/nox/venv/bin/python /workspace/nox/qa_audit.py $p.html > $O/u_qac_$p.out 2>&1; python3 - $p <<'PY' >> $O/u_qac_prog.txt
import json,sys
d=json.load(open('/workspace/nox/web/site/qa/audit.json',encoding='utf-8'))[sys.argv[1]];print(sys.argv[1],d.get('ts'),'wow',d.get('wow'),'ARU',d.get('ARU'),'runs',d.get('vision_runs'),'fails',[f['item'][:34] for f in d.get('fails',[])])
PY
done; echo FIN >> $O/u_qac_prog.txt
AEOF
pgrep -f u_audit6 >/dev/null || { setsid nohup bash $O/u_audit6.sh >/dev/null 2>&1 < /dev/null & }
sleep 1; cat $O/u_qab_prog.txt | cut -c1-260
echo done
