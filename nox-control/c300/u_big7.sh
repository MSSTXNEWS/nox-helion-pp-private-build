echo "C300: u_big7"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s)
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
grep -c "nox-unify.css" finance.html
cp finance.html finance.html.bak_u_$TS
grep -q "nox-unify.css" finance.html || python3 - <<'PYX'
f='finance.html';s=open(f,encoding='utf-8').read();i=s.rfind('</body>');s=s[:i]+'<link rel="stylesheet" href="./nox-unify.css?v=u2">'+s[i:];open(f,'w',encoding='utf-8').write(s);print('link added')
PYX
cat > /tmp/u_f3.py <<'PEOF'
import asyncio
from playwright.async_api import async_playwright
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch();c=await b.new_page(viewport={'width':1440,'height':900});errs=[];c.on('pageerror',lambda e:errs.append(str(e)[:100]))
    await c.goto('http://127.0.0.1:8091/web/finance.html',wait_until='domcontentloaded');await c.wait_for_timeout(5000)
    try: await c.click('.nmc-fab',timeout=2500);print('FAB ok',await c.evaluate("!!document.querySelector('.nmc-fab.on')"),errs[:2])
    except Exception as e: print('FAB ERR',str(e)[:100])
    await b.close()
asyncio.run(m())
PEOF
timeout 60 $PY /tmp/u_f3.py
echo "== audit progress"; cat /tmp/u_qaa_prog.txt; ls -la /tmp/u_audit_*.json 2>/dev/null; tail -5 /tmp/u_qaa_1.out | cut -c1-300
python3 - <<'PYX'
import json,glob
for f in sorted(glob.glob('/tmp/u_audit_*.json'))[:1]:
    d=json.load(open(f));print(f,type(d).__name__,list(d)[:8] if isinstance(d,dict) else len(d))
    s=json.dumps(d,ensure_ascii=False);print(s[:1800])
PYX
