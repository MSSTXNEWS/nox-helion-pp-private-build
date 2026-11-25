PY=/workspace/nox/venv/bin/python
echo "== SU1"
cat > /tmp/s3_su1.py <<'P'
from playwright.sync_api import sync_playwright
JS="""()=>{const s=document.getElementById('nxsun');if(!s)return 'no #nxsun; tb-sun='+!!document.querySelector('.tb-sun');const r=s.getBoundingClientRect();const e=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);return [Math.round(r.left)+','+Math.round(r.top)+' '+Math.round(r.width)+'x'+Math.round(r.height),getComputedStyle(s).display,getComputedStyle(s).pointerEvents,'top:'+(e?e.tagName+'#'+e.id+'.'+e.className.toString().slice(0,24):'none'),'pult:'+!!document.getElementById('nxpult')]}"""
with sync_playwright() as p:
    b=p.chromium.launch()
    for pgn in ('news','photo','index','chat','music'):
        ctx=b.new_context(viewport={'width':1440,'height':900},service_workers='block'); pg=ctx.new_page(); pg.goto('http://localhost:8091/web/%s.html'%pgn,wait_until='load'); pg.wait_for_timeout(5000)
        print('R:',pgn,pg.evaluate(JS)); ctx.close()
    b.close()
P
timeout 100 $PY -I /tmp/s3_su1.py 2>&1 | cut -c1-300
