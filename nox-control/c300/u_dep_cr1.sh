echo "C300: u_dep_cr1"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python; export PATH=/workspace/nox/tools/node/bin:$PATH
curl -fsSL --retry 5 --retry-delay 4 --retry-all-errors https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/u_creative/nox-u-creative.js -o /tmp/nox-u-creative.js && node --check /tmp/nox-u-creative.js && cp /tmp/nox-u-creative.js nox-u-creative.js && echo copied || { echo FAIL; exit 0; }
cp creative.html creative.html.bak_u_$TS; cp nox-k8-draw.js nox-k8-draw.js.bak_u4_$TS
python3 - <<'PYX'
f='creative.html';s=open(f,encoding='utf-8').read()
if './nox-u-creative.js' not in s:
    i=s.rfind('</body>');s=s[:i]+'<script src="./nox-u-creative.js?v=u1" defer></script>'+s[i:];open(f,'w',encoding='utf-8').write(s);print('html added')
f='nox-k8-draw.js';s=open(f,encoding='utf-8').read()
if 'U_LOCALOK' not in s:
    s=s.replace(" const senior={","/* U_LOCALOK */ let lok={t:0,v:true};async function localOk(){if(Date.now()-lok.t<60000)return lok.v;lok.t=Date.now();try{const r=await fetch('/img/health',{cache:'no-store'});const j=await r.json().catch(function(){return{}});lok.v=r.ok&&!(j&&(j.error||j.ok===false||j.disabled))}catch(e){lok.v=false}return lok.v}\n const senior={",1)
    s=s.replace(" async function gen(prompt,sig){"," async function gen(prompt,sig){if(!(await localOk())){const su=await senior.gen(prompt,sig);if(su)return su}",1)
    open(f,'w',encoding='utf-8').write(s);print('draw patched')
PYX
node --check nox-k8-draw.js || { cp nox-k8-draw.js.bak_u4_$TS nox-k8-draw.js; echo ROLLBACK_DRAW; }
sed -i 's#nox-k8-draw.js?v=u[0-9]#nox-k8-draw.js?v=u5#' creative.html
curl -s -m 8 localhost:8091/img/health | head -c 200; echo
cat > /tmp/u_cr5.py <<'PEOF'
import asyncio
from playwright.async_api import async_playwright
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    for w,h in((1440,900),(390,844),(2560,1440)):
      c=await b.new_page(viewport={'width':w,'height':h});errs=[];c.on('pageerror',lambda e:errs.append(str(e)[:100]))
      await c.goto('http://127.0.0.1:8091/web/creative.html',wait_until='domcontentloaded');await c.wait_for_timeout(6000)
      r=await c.evaluate("(()=>{try{const cv=NOXDZ.cv;const st=document.getElementById('dzStage').getBoundingClientRect();return [document.querySelectorAll('.u-fab').length,!!document.querySelector('.u-empty'),Math.round(cv.getZoom()*100),Math.round(st.width),document.documentElement.scrollWidth<=innerWidth,typeof K8draw.senior.gen]}catch(e){return 'EXC '+e}})()")
      print('QA',w,r,errs[:2],flush=True)
      if w==1440: await c.screenshot(path='/tmp/u_cr5.jpg',type='jpeg',quality=55)
      await c.close()
    await b.close()
asyncio.run(m())
PEOF
timeout 100 $PY /tmp/u_cr5.py | tee /tmp/u_cr5.out
grep -E "^QA" /tmp/u_cr5.out | grep -q "Unexpected\|Error\|EXC" && { cp creative.html.bak_u_$TS creative.html; cp nox-k8-draw.js.bak_u4_$TS nox-k8-draw.js; echo ROLLBACK; } || echo QA_CLEAN
echo "U: студия дизайна: большое полотно по центру, стекло, фабы в шапке чата, живое пустое состояние; gen: preflight /img/health -> старший советник" >> qa/rework/creative.fixed
echo "== qa_audit progress"; cat /workspace/nox/agent/out/u_qaa_prog.txt 2>/dev/null; ls -la /workspace/nox/agent/out | grep u_qaa; python3 - <<'PYX'
import json
a=json.load(open('/workspace/nox/web/site/qa/audit.json',encoding='utf-8'))
for p in ('creative','settings','index','chat'):
    d=a.get(p) or {};print(p,d.get('ts'),'wow',d.get('wow'),'ARU',d.get('ARU'),'runs',d.get('vision_runs'))
PYX
echo done
