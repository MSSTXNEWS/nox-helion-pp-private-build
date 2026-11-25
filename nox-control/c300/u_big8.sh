echo "C300: u_big8"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s); O=/workspace/nox/agent/out
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
echo "== uptime"; uptime -p; ls /tmp | head -3
echo "== fab css cascade"; grep -n "nmc-fab" nox-unify.css | cut -c1-200 | tail -5; grep -l "nmc-fab" *.css | head
cp nox-unify.css nox-unify.css.bak_u3_$TS
grep -q U_FABUP3 nox-unify.css || printf '\n/* U_FABUP3 */\n@media (min-width:769px){html:not(#u) body:has(.nai-btn,#nxnavx) button.nmc-fab{bottom:calc(var(--ds-dock-h,0px) + var(--ds-safe-b,0px) + 76px) !important}}\n' >> nox-unify.css
sed -i -E 's#nox-unify\.css\?v=[A-Za-z0-9_]+#nox-unify.css?v=u3#' *.html
timeout 60 $PY /tmp/u_f3.py 2>&1 | head -3 || true
cat > /tmp/u_f3.py <<'PEOF'
import asyncio
from playwright.async_api import async_playwright
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    for pg in ('finance','mail','news'):
      c=await b.new_page(viewport={'width':1440,'height':900})
      await c.goto('http://127.0.0.1:8091/web/%s.html'%pg,wait_until='domcontentloaded');await c.wait_for_timeout(5000)
      info=await c.evaluate("(()=>{const f=document.querySelector('.nmc-fab');const b=f.getBoundingClientRect();return [getComputedStyle(f).bottom,b.top|0,[...document.styleSheets].map(s=>s.href&&s.href.split('/').pop()).filter(x=>x&&/unify/.test(x))]})()")
      try: await c.click('.nmc-fab',timeout=2500);r='ok'
      except Exception as e: r='ERR'
      print('FAB',pg,r,info,flush=True);await c.close()
    await b.close()
asyncio.run(m())
PEOF
timeout 80 $PY /tmp/u_f3.py
echo "== start audit (setsid)"
cat > $O/u_audit3.sh <<'AEOF'
cd /workspace/nox/web/site
O=/workspace/nox/agent/out; rm -f $O/u_qaa_*
for i in 1 2 3; do /workspace/nox/venv/bin/python /workspace/nox/qa_audit.py creative.html settings.html index.html chat.html > $O/u_qaa_$i.out 2>&1; cp qa/audit.json $O/u_qaa_$i.json 2>/dev/null; echo "run $i done $(date +%T)" >> $O/u_qaa_prog.txt; done
echo FIN >> $O/u_qaa_prog.txt
AEOF
setsid nohup bash $O/u_audit3.sh >/dev/null 2>&1 < /dev/null &
sleep 3; pgrep -f qa_audit | head -2
echo done
