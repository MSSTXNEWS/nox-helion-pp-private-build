echo "C300: u_dep_board3"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python; export PATH=/workspace/nox/tools/node/bin:$PATH
curl -fsSL --retry 5 --retry-delay 4 --retry-all-errors https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/u_board/nox-u-board.js -o /tmp/nox-u-board.js && node --check /tmp/nox-u-board.js && cp nox-u-board.js nox-u-board.js.bak_u3_$TS && cp /tmp/nox-u-board.js nox-u-board.js && echo copied || { echo FAIL; exit 0; }
sed -i "s#nox-u-board.js?v=u[0-9]#nox-u-board.js?v=u4#" chat.html
echo "== live API via proxy"; for p in /board /worms/cards /worms/learned /lessons /worms/agenda; do echo "$p $(curl -s -m 8 -o /tmp/u_o.txt -w '%{http_code}' localhost:8091/svc/agentsb$p) $(head -c 120 /tmp/u_o.txt | tr '\n' ' ')"; done
cat > /tmp/u_b3.py <<'PEOF'
import asyncio
from playwright.async_api import async_playwright
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    for w,h in((1440,900),(390,844)):
      c=await b.new_page(viewport={'width':w,'height':h});errs=[];c.on('pageerror',lambda e:errs.append(str(e)[:100]))
      await c.goto('http://127.0.0.1:8091/web/chat.html'+('?home=0' if w<500 else ''),wait_until='domcontentloaded');await c.wait_for_timeout(5500)
      r=await c.evaluate("(()=>{const e=document.getElementById('nox-u-board');if(!e)return null;const t=[...e.querySelectorAll('[data-tab]')].map(x=>x.innerText.replace(/\\n/g,''));return [e.parentElement.className.slice(0,14),t,e.querySelector('.ub-body').innerText.slice(0,80).replace(/\\n/g,' | ')]})()")
      print('QA',w,r,errs[:2],flush=True)
      if w==1440: await c.screenshot(path='/tmp/u_b3.jpg',type='jpeg',quality=50)
      await c.close()
    await b.close()
asyncio.run(m())
PEOF
timeout 80 $PY /tmp/u_b3.py | tee /tmp/u_b3.out
grep "QA 1440" /tmp/u_b3.out | grep -q "\[\]$" || { cp nox-u-board.js.bak_u3_$TS nox-u-board.js; sed -i "s#nox-u-board.js?v=u4#nox-u-board.js?v=u3#" chat.html; echo ROLLBACK; }
echo "U: панель NOX: задачи/карточки worms/идеи/выучено, отмена, подумай глубже" >> qa/rework/chat.fixed
echo "== qa_audit progress"; cat /workspace/nox/agent/out/u_qaa_prog.txt 2>/dev/null; tail -c 400 /workspace/nox/agent/out/u_qaa_1.out
echo done
