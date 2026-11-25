echo "C300: u_dep_h1"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python; export PATH=/workspace/nox/tools/node/bin:$PATH
curl -fsSL --retry 5 --retry-delay 4 --retry-all-errors https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/u_hints/nox-u-hints.js -o /tmp/nox-u-hints.js && node --check /tmp/nox-u-hints.js && cp /tmp/nox-u-hints.js nox-u-hints.js && echo copied || { echo FAIL; exit 0; }
cp settings.html settings.html.bak_u4_$TS
python3 - <<'PYX'
f='settings.html';s=open(f,encoding='utf-8').read()
if './nox-u-hints.js' not in s:
    i=s.rfind('</body>');s=s[:i]+'<script src="./nox-u-hints.js?v=u1" defer></script>'+s[i:];open(f,'w',encoding='utf-8').write(s);print('hints added')
PYX
echo "U: settings: подсказки при наведении + Alt+клик спросить NOX" >> qa/rework/settings.fixed
echo "== источник emo в бэкенде"; grep -rn "\"emo\"\|'emo'\|meta.emo\|\"emotion\"" /workspace/nox/web/pkg/server/*.py /workspace/nox/agent/*.py 2>/dev/null | head -6 | cut -c1-200; curl -s -m 5 localhost:8091/api/chat/health | head -c 200; echo
cat > /tmp/u_chk.py <<'PEOF'
import asyncio
from playwright.async_api import async_playwright
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    c=await b.new_page(viewport={'width':1440,'height':900});errs=[];c.on('pageerror',lambda e:errs.append(str(e)[:100]))
    await c.goto('http://127.0.0.1:8091/web/index.html',wait_until='domcontentloaded');await c.wait_for_timeout(4500)
    r=await c.evaluate("""(async()=>{const o={};K8meta.handle({meta:{emo:'радость',confidence:.7}});o.glow=getComputedStyle(document.documentElement).getPropertyValue('--k8-glow');const bs=getComputedStyle(document.body,'::after').boxShadow;o.after=bs.slice(0,60);
      o.sr=!!(window.SpeechRecognition||window.webkitSpeechRecognition);o.tts='speechSynthesis' in window;
      let aborted=false;const pr=K8voice.run(sig=>new Promise((res,rej)=>{sig.addEventListener('abort',()=>{aborted=true;rej(new Error('abort'))})}));await new Promise(r=>setTimeout(r,200));o.busy=K8voice.busy();const stopBtn=document.getElementById('k8-stop');o.btnShown=!!stopBtn&&!stopBtn.hidden;K8voice.stop();await pr;o.aborted=aborted;o.busyAfter=K8voice.busy();o.dkStop=!!document.getElementById('dkStop');return JSON.stringify(o)})()""")
    print('QA',r,errs[:2],flush=True)
    c2=await b.new_page(viewport={'width':1440,'height':900});e2=[];c2.on('pageerror',lambda e:e2.append(str(e)[:100]))
    await c2.goto('http://127.0.0.1:8091/web/settings.html',wait_until='domcontentloaded');await c2.wait_for_timeout(4500)
    await c2.hover('button:has-text("Голос")');await c2.wait_for_timeout(900)
    print('QA settings hint',await c2.evaluate("(document.getElementById('u-hint')||{}).innerText"),e2[:2],flush=True)
    await b.close()
asyncio.run(m())
PEOF
timeout 100 $PY /tmp/u_chk.py | tee /tmp/u_chk.out
grep -E "^QA" /tmp/u_chk.out | grep -q "Unexpected\|Error" && { cp settings.html.bak_u4_$TS settings.html; echo ROLLBACK; } || echo QA_CLEAN
echo "== audit progress"; cat /workspace/nox/agent/out/u_qab_prog.txt 2>/dev/null; pgrep -af qa_audit | cut -c1-90
echo done
