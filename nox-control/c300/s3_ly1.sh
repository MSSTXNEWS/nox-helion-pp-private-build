#!/bin/bash
S=/workspace/nox/web/site; PY=/workspace/nox/venv/bin/python
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
for f in ly-add.css ly-add.js; do curl -fsSL "$RAW/$f?v=$(date +%s)" -o /tmp/s3ly_$f || { echo FETCHFAIL $f; exit 1; }; done
cp $S/nox-ds.css $S/nox-ds.css.bak_s3_16; cp $S/nox-ds.js $S/nox-ds.js.bak_s3_16
grep -q "S3 слои" $S/nox-ds.css || cat /tmp/s3ly_ly-add.css >> $S/nox-ds.css
grep -q "S3 слои" $S/nox-ds.js || cat /tmp/s3ly_ly-add.js >> $S/nox-ds.js
$PY /workspace/nox/qa_ctl.py --pin
cat > /tmp/s3_ly1.py <<'P'
from playwright.sync_api import sync_playwright
JS="""()=>{const R=e=>e.getBoundingClientRect();const hd=document.querySelector('.bar.tb'),dk=document.getElementById('nxdock');if(!hd||!dk)return 'no hd/dk';const H=R(hd),D=R(dk);const ov=(a,b)=>Math.max(0,Math.min(a.right,b.right)-Math.max(a.left,b.left))*Math.max(0,Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top));
const out=[];for(const e of document.querySelectorAll('body *')){const s=getComputedStyle(e);if(s.position!='fixed'||e===hd||e===dk||e.id=='nxsun'||e.closest('#nxdock,.bar.tb,#nxpult,ninja-keys'))continue;const r=R(e);if(r.width<20||r.height<20||s.visibility=='hidden'||s.display=='none'||+s.opacity==0)continue;if(e.id=='space'||e.id=='dust'||/grain|vignette|nox-fx/.test(e.className.toString()+e.id)||r.height>=innerHeight*.9)continue;const a=ov(r,H),b=ov(r,D);if(a>0||b>0)out.push((e.id||e.className.toString().slice(0,20))+' hdr'+Math.round(a)+' dock'+Math.round(b))}
const pg=document.getElementById('page');return {dockH:Math.round(D.height),headH:Math.round(H.height),padB:pg&&getComputedStyle(pg).paddingBottom,overlaps:out}}"""
with sync_playwright() as p:
    b=p.chromium.launch()
    for w,h in ((1440,900),(390,844)):
        for pgn in ('index','chat','photo','news','music','settings'):
            ctx=b.new_context(viewport={'width':w,'height':h},service_workers='block'); pg=ctx.new_page()
            try:
                pg.goto('http://localhost:8091/web/%s.html'%pgn,wait_until='load'); pg.wait_for_timeout(3500); print('R:',w,pgn,pg.evaluate(JS))
            except Exception as e: print('R:',w,pgn,'ERR',str(e)[:80])
            ctx.close()
    b.close()
P
timeout 240 $PY -I /tmp/s3_ly1.py 2>&1 | cut -c1-400
