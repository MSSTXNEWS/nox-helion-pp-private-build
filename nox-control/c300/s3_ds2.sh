#!/bin/bash
S=/workspace/nox/web/site; PY=/workspace/nox/venv/bin/python
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
for f in ds2-add.js ds2-add.css; do curl -fsSL "$RAW/$f?v=$(date +%s)" -o /tmp/s3d2_$f || { echo FETCHFAIL $f; exit 1; }; done
cp $S/nox-ds.js $S/nox-ds.js.bak_s3_15; cp $S/nox-ds.css $S/nox-ds.css.bak_s3_15; cp $S/nox-set-search.js $S/nox-set-search.js.bak_s3_15
grep -q "S3 ds2" $S/nox-ds.js || cat /tmp/s3d2_ds2-add.js >> $S/nox-ds.js
grep -q "ds-skel-set" $S/nox-ds.css || cat /tmp/s3d2_ds2-add.css >> $S/nox-ds.css
echo "-- rIC usages:"; grep -ln "requestIdleCallback" $S/*.js | head -20
$PY - <<'P'
import re,glob
n=0
for f in glob.glob('/workspace/nox/web/site/*.js'):
    if f.endswith(('.min.js',)) : continue
    s=open(f,encoding='utf-8',errors='replace').read()
    t=re.sub(r'\(window\.requestIdleCallback \|\| setTimeout\)\((\w+), (\d+)\)',r'(window.requestIdleCallback ? function (f) { window.requestIdleCallback(f, { timeout: 500 }); } : setTimeout)(\1, \2)',s)
    t=re.sub(r'\brequestIdleCallback\((\w+), *(\d+)\)',r'requestIdleCallback(\1, { timeout: \2 })',t)
    if t!=s: open(f,'w',encoding='utf-8').write(t); n+=1; print('fixed',f.split('/')[-1])
print('rIC fixed files',n)
# группы в сайдбаре настроек
f='/workspace/nox/web/site/nox-set-search.js'; s=open(f,encoding='utf-8').read()
if 'nxm-grp' not in s.replace('.nxm-grp','x'):
    add="""    const G = { personality: 'Ассистент', ui: 'Система' };
    Object.entries(G).forEach(([k, t]) => { const b = side.querySelector('[role=tab][data-tab="' + k + '"]'); if (b && !side.querySelector('.nxm-grp[data-g="' + k + '"]')) { const h = document.createElement('div'); h.className = 'nxm-grp'; h.dataset.g = k; h.textContent = t; side.insertBefore(h, b); } });
"""
    s=s.replace("    const secs = () =>",add+"    const secs = () =>",1); open(f,'w',encoding='utf-8').write(s); print('groups added')
P
$PY /workspace/nox/qa_ctl.py --pin
cat > /tmp/s3_ds2.py <<'P'
from playwright.sync_api import sync_playwright
import glob,os
pages=['index','music','news','studio','cinema','settings','chat','board','glance','creative','scene','effects','voice','dispatcher']
with sync_playwright() as p:
    b=p.chromium.launch(); bad=[]
    for pgn in pages:
        ctx=b.new_context(viewport={'width':1440,'height':900},service_workers='block'); pg=ctx.new_page(); errs=[]; pg.on('pageerror',lambda e: errs.append(str(e)[:120]))
        try:
            pg.goto('http://localhost:8091/web/%s.html'%pgn,wait_until='load'); pg.wait_for_timeout(3500)
            r=pg.evaluate("()=>({ds:!!window.NOXds,css:!!document.querySelector('link[href*=\"nox-ds.css\"]')})")
        except Exception as e: r=str(e)[:80]
        print('R:',pgn,r,errs[:2]); ctx.close()
    ctx=b.new_context(viewport={'width':1440,'height':900},service_workers='block'); pg=ctx.new_page(); pg.goto('http://localhost:8091/web/settings.html',wait_until='load'); pg.wait_for_timeout(4000)
    print('R: groups', pg.evaluate("()=>[...document.querySelectorAll('.nxm-grp')].map(e=>e.textContent)"))
    b.close()
P
timeout 200 $PY -I /tmp/s3_ds2.py 2>&1 | cut -c1-400
