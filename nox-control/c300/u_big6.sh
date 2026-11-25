echo "C300: u_big6"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python; export PATH=/workspace/nox/tools/node/bin:$PATH
echo "== 0 security: 8091 local, 18091 -> 401, 8080 -> 404: без изменений"
echo "== 1 board in .cx-right"
curl -fsSL --retry 5 --retry-delay 4 --retry-all-errors https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/u_board/nox-u-board.js -o /tmp/nox-u-board.js && node --check /tmp/nox-u-board.js && cp nox-u-board.js nox-u-board.js.bak_u_$TS && cp /tmp/nox-u-board.js nox-u-board.js && echo copied
sed -i "s#nox-u-board.js?v=u2#nox-u-board.js?v=u3#" chat.html
echo "== 2 css: fab над .nai-btn, кнопки бюджета 44"
cp nox-unify.css nox-unify.css.bak_u2_$TS; cp nox-k8-ui.css nox-k8-ui.css.bak_u2_$TS
grep -q U_FABUP2 nox-unify.css || printf '\n/* U_FABUP2 */\n@media (min-width:769px){body:has(.nai-btn) .nmc-fab{bottom:calc(var(--ds-dock-h,0px) + var(--ds-safe-b,0px) + 76px) !important}}\n' >> nox-unify.css
grep -q U_BUD44 nox-k8-ui.css || printf '\n/* U_BUD44 */\n#k8-budget-d button,#k8-budget-d input,#k8-annot-d button,#k8-anki-d button,#k8-night-d button{min-height:44px}\n#nox-u-board.in{margin:8px 0}\n' >> nox-k8-ui.css
sed -i -E 's#nox-unify\.css\?v=[A-Za-z0-9_]+#nox-unify.css?v=u2#; ' *.html; sed -i -E 's#nox-k8-ui\.css\?v=[A-Za-z0-9_]+#nox-k8-ui.css?v=u2#' *.html
echo "== 3 QA"
cat > /tmp/u_v6.py <<'PEOF'
import asyncio
from playwright.async_api import async_playwright
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    for pg in ('finance','chat','mail'):
      c=await b.new_page(viewport={'width':1440,'height':900});errs=[];c.on('pageerror',lambda e:errs.append(str(e)[:100]))
      await c.goto('http://127.0.0.1:8091/web/%s.html'%pg,wait_until='domcontentloaded');await c.wait_for_timeout(5000)
      try: await c.click('.nmc-fab',timeout=2500);ok=await c.evaluate("!!document.querySelector('.nmc-fab.on')")
      except Exception as e: ok='ERR'
      ex=await c.evaluate("(()=>{const e=document.getElementById('nox-u-board');return e?[e.parentElement.className.slice(0,20),e.classList.contains('fl'),e.innerText.length]:null})()")
      print('QA',pg,'fab',ok,'board',ex,errs[:2],flush=True)
      if pg=='finance':
        await c.evaluate("window.K8budget&&K8budget.open()");await c.wait_for_timeout(800)
        print('QA budget minh',await c.evaluate("Math.min(...[...document.querySelectorAll('#k8-budget-d button,#k8-budget-d input')].filter(x=>x.offsetParent).map(x=>Math.round(x.getBoundingClientRect().height)))"))
      await c.close()
    await b.close()
asyncio.run(m())
PEOF
timeout 100 $PY /tmp/u_v6.py
echo "== 4 background: qa_audit x3 (creative settings index chat)"
cat > /tmp/u_audit3.sh <<'AEOF'
cd /workspace/nox/web/site
for i in 1 2 3; do /workspace/nox/venv/bin/python /workspace/nox/qa_audit.py creative.html settings.html index.html chat.html > /tmp/u_qaa_$i.out 2>&1; cp qa/audit.json /tmp/u_audit_$i.json 2>/dev/null; echo "run $i done" >> /tmp/u_qaa_prog.txt; done
echo FIN >> /tmp/u_qaa_prog.txt
AEOF
rm -f /tmp/u_qaa_prog.txt; nohup bash /tmp/u_audit3.sh >/dev/null 2>&1 &
echo "u_big6 done"
