S=/workspace/nox/web/site; PY=/workspace/nox/venv/bin/python
echo "== FX18"; sed -n 330,345p $S/nav.json | cut -c1-160; sed -n 484,492p $S/nav.json
cp $S/nox-planets3d.js $S/nox-planets3d.js.bak_s3_13
$PY - <<'P'
f='/workspace/nox/web/site/nox-planets3d.js'; s=open(f,encoding='utf-8').read()
o="(window.requestIdleCallback || setTimeout)(boot, 50);"; assert o in s
open(f,'w',encoding='utf-8').write(s.replace(o,"if (window.requestIdleCallback) window.requestIdleCallback(boot, { timeout: 500 }); else setTimeout(boot, 50);")); print('idle fixed')
P
$PY /workspace/nox/qa_ctl.py --pin
cat > /tmp/s3_fx18.py <<'P'
import base64,subprocess
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); ctx=b.new_context(viewport={'width':1440,'height':900},service_workers='block'); pg=ctx.new_page(); reqs=[]; errs=[]
    pg.on('pageerror',lambda e: print('R: pageerror',str(e)[:200])); pg.on('request',lambda r: reqs.append(r.url.split('/planets/')[-1]) if '/planets/' in r.url else None); pg.on('response',lambda r: errs.append(r.url[-40:]) if r.status>=400 else None)
    pg.goto('http://localhost:8091/web/settings.html',wait_until='load'); pg.wait_for_timeout(3000)
    print('R: load', pg.evaluate("()=>Math.round(performance.getEntriesByType('navigation')[0].loadEventEnd)"), 'planet reqs before', len(reqs))
    pg.evaluate("()=>[...document.querySelectorAll('.nxm-side [role=tab]')].find(b=>/Интерфейс/.test(b.textContent)).click()"); pg.wait_for_timeout(1500)
    pg.evaluate("()=>{const e=document.querySelector('.nxpl');e&&e.scrollIntoView({block:'center'})}"); pg.wait_for_timeout(9000)
    print('R:', pg.evaluate("()=>[(document.querySelector('.nxpl-n')||{}).textContent, document.querySelectorAll('.nxpl-g canvas').length]"), sorted(set(reqs)), errs)
    pg.screenshot(path='/tmp/s.png'); subprocess.run(['ffmpeg','-loglevel','error','-y','-i','/tmp/s.png','-vf','scale=1000:-1','-q:v','8','/tmp/s.jpg'])
    print('B64_BEGIN'); print(base64.b64encode(open('/tmp/s.jpg','rb').read()).decode()); print('B64_END'); b.close()
P
timeout 120 $PY -I /tmp/s3_fx18.py 2>&1 | fold -w 900
