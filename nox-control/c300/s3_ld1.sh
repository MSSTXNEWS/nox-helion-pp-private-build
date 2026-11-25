#!/bin/bash
S=/workspace/nox/web/site; PY=/workspace/nox/venv/bin/python
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
for f in ld.js sleep.js; do curl -fsSL "$RAW/$f?v=$(date +%s)" -o /tmp/s3ld_$f || { echo FETCHFAIL $f; exit 1; }; done
cp $S/nox-dock-pop.js $S/nox-dock-pop.js.bak_s3_28; cp $S/nox-ds.js $S/nox-ds.js.bak_s3_28
grep -q "S3-LOAD" $S/nox-dock-pop.js || { cat /tmp/s3ld_ld.js $S/nox-dock-pop.js > /tmp/s3ld_dp.js && cp /tmp/s3ld_dp.js $S/nox-dock-pop.js; }
grep -q "честная пометка" $S/nox-ds.js || cat /tmp/s3ld_sleep.js >> $S/nox-ds.js
sed -i 's#nox-ds\.js?v=s3e#nox-ds.js?v=s3f#g; s#nox-dock-pop\.js"#nox-dock-pop.js?v=s3f"#g' $S/*.html $S/nox-dock-pop.js
$PY /workspace/nox/qa_ctl.py --pin
head -c 120 $S/nox-dock-pop.js; echo
cat > /tmp/s3_ld1.py <<'P'
from playwright.sync_api import sync_playwright
OBS="""()=>{window.__m=0;window.__mo&&window.__mo.disconnect();window.__mo=new MutationObserver(l=>{window.__m+=l.length});window.__mo.observe(document.documentElement,{subtree:true,childList:true,attributes:true,characterData:true})}"""
with sync_playwright() as p:
    b=p.chromium.launch()
    for pgn in ('news','music','studio','cinema','photo'):
        ctx=b.new_context(viewport={'width':1440,'height':900},service_workers='block'); pg=ctx.new_page(); errs=[]; reqs=[]
        pg.on('pageerror',lambda e: errs.append(str(e)[:80])); pg.on('request',lambda r: reqs.append(r.method+' '+r.url.split('localhost:8091')[-1][:26]) if '/api/' in r.url else None)
        pg.goto('http://localhost:8091/web/%s.html'%pgn,wait_until='load'); pg.wait_for_timeout(5000)
        if not pg.evaluate("()=>!!document.getElementById('nxsun')"): print('R:',pgn,'NO SUN'); ctx.close(); continue
        pg.click('#nxsun',timeout=8000); pg.wait_for_timeout(900)
        n=pg.evaluate("()=>document.querySelectorAll('#nxpult button').length"); dead=[]; 
        for i in range(n):
            info=pg.evaluate("(i)=>{const b=document.querySelectorAll('#nxpult button')[i];return [(b.textContent||b.getAttribute('aria-label')||'').trim().slice(0,20),b.disabled,getComputedStyle(b).display]}",i)
            if info[2]=='none': continue
            pg.evaluate(OBS); reqs.clear(); e0=len(errs)
            pg.evaluate("(i)=>document.querySelectorAll('#nxpult button')[i].click()",i); pg.wait_for_timeout(700)
            m=pg.evaluate("()=>window.__m")
            if m==0 and not reqs and len(errs)==e0: dead.append(info[0])
            if pg.evaluate("()=>!!document.fullscreenElement"): pg.keyboard.press('Escape')
            if not pg.evaluate("()=>{const e=document.querySelector('#nxpult .nxpu-stop');return !!e&&e.getBoundingClientRect().width>0}"): pg.click('#nxsun'); pg.wait_for_timeout(600)
        print('R:',pgn,'pult buttons',n,'dead',dead,'sleep-note',pg.evaluate("()=>[...document.querySelectorAll('#nxpult .ds-badge-off')].map(e=>e.textContent)"),'errs',errs[:2]); ctx.close()
    b.close()
P
timeout 250 $PY -I /tmp/s3_ld1.py 2>&1 | cut -c1-300
