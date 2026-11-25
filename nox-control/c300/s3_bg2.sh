#!/bin/bash
S=/workspace/nox/web/site; PY=/workspace/nox/venv/bin/python
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
curl -fsSL "$RAW/bg-add.css?v=$(date +%s)" -o /tmp/s3bg.css || exit 1
cp $S/nox-ds.css $S/nox-ds.css.bak_s3_18
grep -q "S3 слои фона" $S/nox-ds.css || cat /tmp/s3bg.css >> $S/nox-ds.css
$PY /workspace/nox/qa_ctl.py --pin
cat > /tmp/s3_bg2.py <<'P'
import base64,subprocess
from playwright.sync_api import sync_playwright
JS="""()=>{const a=document.getElementById('nox-fx-ash');const s=a?getComputedStyle(a):null;const app=document.getElementById('app');const card=document.querySelector('.card');const e=card&&document.elementFromPoint(card.getBoundingClientRect().left+60,Math.min(card.getBoundingClientRect().top+30,innerHeight-60));return {ash:s&&[s.position,s.zIndex,s.pointerEvents],app:getComputedStyle(app).zIndex,top:e&&(e.tagName+'.'+e.className.toString().slice(0,20)),blur:card&&getComputedStyle(card).backdropFilter}}"""
with sync_playwright() as p:
    b=p.chromium.launch()
    for pgn in ('system','index','music','news','chat','settings'):
        ctx=b.new_context(viewport={'width':1440,'height':900},service_workers='block'); pg=ctx.new_page(); pg.goto('http://localhost:8091/web/%s.html'%pgn,wait_until='load'); pg.wait_for_timeout(4500)
        print('R:',pgn,pg.evaluate(JS))
        if pgn=='system':
            pg.screenshot(path='/tmp/s.png'); subprocess.run(['ffmpeg','-loglevel','error','-y','-i','/tmp/s.png','-vf','scale=1000:-1','-q:v','8','/tmp/s.jpg'])
            print('B64_BEGIN'); print(base64.b64encode(open('/tmp/s.jpg','rb').read()).decode()); print('B64_END')
        ctx.close()
    b.close()
P
timeout 150 $PY -I /tmp/s3_bg2.py 2>&1 | fold -w 900
