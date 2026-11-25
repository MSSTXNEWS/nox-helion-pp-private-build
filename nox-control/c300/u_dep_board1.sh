echo "C300: u_dep_board1"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python; export PATH=/workspace/nox/tools/node/bin:$PATH
curl -fsSL --retry 5 --retry-delay 4 --retry-all-errors https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/u_board/nox-u-board.js -o /tmp/nox-u-board.js && node --check /tmp/nox-u-board.js && cp /tmp/nox-u-board.js nox-u-board.js && echo copied || { echo FAIL_FETCH; exit 0; }
cp chat.html chat.html.bak_u_$TS
python3 - <<'PYX'
f='chat.html';s=open(f,encoding='utf-8').read()
if './nox-u-board.js' not in s:
    t='<link rel="stylesheet" href="./nox-k8-ui.css?v=k8b"><script src="./nox-u-board.js?v=u1" defer></script>' if 'nox-k8-ui.css' not in s else '<script src="./nox-u-board.js?v=u1" defer></script>'
    i=s.rfind('</body>');s=s[:i]+t+s[i:];open(f,'w',encoding='utf-8').write(s);print('added')
PYX
echo "U: виджет «В работе / Нужен ты / Готово» (канбан агентов)" >> qa/rework/chat.fixed
cat > /tmp/u_b.py <<'PEOF'
import asyncio
from playwright.async_api import async_playwright
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    for w,h,u in((1440,900,'chat.html'),(390,844,'chat.html')):
      c=await b.new_page(viewport={'width':w,'height':h});errs=[];c.on('pageerror',lambda e:errs.append(str(e)[:100]))
      await c.goto('http://127.0.0.1:8091/web/'+u,wait_until='domcontentloaded');await c.wait_for_timeout(4500)
      print('QA',w,await c.evaluate("(()=>{const e=document.getElementById('nox-u-board');return e?e.innerText.slice(0,160).replace(/\\n/g,' | '):null})()"),errs[:2],flush=True);await c.close()
    await b.close()
asyncio.run(m())
PEOF
timeout 80 $PY /tmp/u_b.py | tee /tmp/u_b.out
grep -q "\[\]" /tmp/u_b.out || { cp chat.html.bak_u_$TS chat.html; echo ROLLBACK; }
echo done
