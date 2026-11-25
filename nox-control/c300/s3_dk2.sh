#!/bin/bash
S=/workspace/nox/web/site; PY=/workspace/nox/venv/bin/python
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
for f in dk-add.css dk-add.js; do curl -fsSL "$RAW/$f?v=$(date +%s)" -o /tmp/s3dk_$f || { echo FETCHFAIL $f; exit 1; }; done
cp $S/nox-ds.css $S/nox-ds.css.bak_s3_17; cp $S/nox-ds.js $S/nox-ds.js.bak_s3_17; cp $S/nox-unify.css $S/nox-unify.css.bak_s3_17
grep -q "S3 док: один ряд" $S/nox-ds.css || cat /tmp/s3dk_dk-add.css >> $S/nox-ds.css
grep -q "S3 док/шрифты" $S/nox-ds.js || cat /tmp/s3dk_dk-add.js >> $S/nox-ds.js
sed -i 's/font-size:10px!important;gap:4px!important/font-size:12px!important;gap:4px!important/; s/letter-spacing:.02em!important;font-size:12px/letter-spacing:0!important;font-size:12px/' $S/nox-unify.css
sed -i 's#nox-ds\.css?v=s3a#nox-ds.css?v=s3b#g; s#nox-ds\.js?v=s3a#nox-ds.js?v=s3b#g' $S/*.html $S/nox-dock-pop.js
$PY /workspace/nox/qa_ctl.py --pin
cat > /tmp/s3_dk2.py <<'P'
import json,collections,base64,subprocess
from playwright.sync_api import sync_playwright
n=json.load(open('/workspace/nox/web/site/nav.json',encoding='utf-8'))
files=[i['file'] for g in n['groups'] for i in g['items']]
JS="""()=>{const o={};for(const e of document.querySelectorAll('body *')){if(e.closest('ninja-keys,svg,canvas,.excalidraw'))continue;let t='';for(const c of e.childNodes)if(c.nodeType==3)t+=c.textContent;t=t.trim();if(!t)continue;const r=e.getBoundingClientRect();if(!r.width||!r.height)continue;const s=getComputedStyle(e);if(s.visibility=='hidden'||s.display=='none')continue;if(parseFloat(s.fontSize)<12){const k=e.tagName.toLowerCase()+'.'+(e.className&&e.className.toString?e.className.toString().split(' ')[0]:'')+'@'+s.fontSize;o[k]=(o[k]||0)+1}}return o}"""
GEO="""()=>{const L=[...document.querySelectorAll('.tb-l > *')].filter(c=>getComputedStyle(c).display!='none'),Rr=[...document.querySelectorAll('.tb-r > *')].filter(c=>getComputedStyle(c).display!='none');const cells=[...document.querySelectorAll('#nxdock .nxd-cells a')];const d=document.getElementById('nxdock').getBoundingClientRect();const st=[...document.querySelectorAll('#nxdTools button')].filter(b=>getComputedStyle(b).display!='none').map(b=>b.textContent.trim().slice(0,8));return {hdrL:Math.round(Math.min(...L.map(c=>c.getBoundingClientRect().left))),hdrR:Math.round(Math.max(...Rr.map(c=>c.getBoundingClientRect().right))),w:innerWidth,dockH:Math.round(d.height),cellsL:Math.round(Math.min(...cells.map(c=>c.getBoundingClientRect().left))),cellsR:Math.round(Math.max(...cells.map(c=>c.getBoundingClientRect().right))),n:cells.length,tools:st}}"""
tot=collections.Counter()
with sync_playwright() as p:
    b=p.chromium.launch()
    for w in (1280,1440,1920):
        ctx=b.new_context(viewport={'width':w,'height':900},service_workers='block'); pg=ctx.new_page(); pg.goto('http://localhost:8091/web/music.html',wait_until='load'); pg.wait_for_timeout(4000); print('R: geo',w,pg.evaluate(GEO)); ctx.close()
    ctx=b.new_context(viewport={'width':1440,'height':900},service_workers='block'); pg=ctx.new_page(); pg.goto('http://localhost:8091/web/index.html',wait_until='load'); pg.wait_for_timeout(4500)
    pg.screenshot(path='/tmp/s.png'); subprocess.run(['ffmpeg','-loglevel','error','-y','-i','/tmp/s.png','-vf','scale=1000:-1','-q:v','8','/tmp/s.jpg'])
    print('B64_BEGIN'); print(base64.b64encode(open('/tmp/s.jpg','rb').read()).decode()); print('B64_END'); ctx.close()
    for f in files:
        ctx=b.new_context(viewport={'width':1440,'height':900},service_workers='block'); pg=ctx.new_page()
        try:
            pg.goto('http://localhost:8091/web/%s'%f,wait_until='load',timeout=20000); pg.wait_for_timeout(4000); o=pg.evaluate(JS)
            for k,v in o.items(): tot[k]+=v
            print('R:',f,sum(o.values()))
        except Exception as e: print('R:',f,'ERR',str(e)[:60])
        ctx.close()
    b.close()
print('R: TOP', tot.most_common(20))
P
timeout 290 $PY -I /tmp/s3_dk2.py 2>&1 | cut -c1-900
