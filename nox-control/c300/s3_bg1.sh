PY=/workspace/nox/venv/bin/python
echo "== BG1"
cat > /tmp/s3_bg1.py <<'P'
from playwright.sync_api import sync_playwright
JS="""()=>{const out=[];for(const c of document.querySelectorAll('canvas,#space,#dust,.grain,.vignette,#app,#page,.wrap')){const s=getComputedStyle(c),r=c.getBoundingClientRect();out.push((c.tagName+(c.id?'#'+c.id:'')+'.'+c.className.toString().slice(0,22)+' pos='+s.position+' z='+s.zIndex+' '+Math.round(r.width)+'x'+Math.round(r.height)+' top'+Math.round(r.top)+' par='+(c.parentElement?c.parentElement.tagName+(c.parentElement.id?'#'+c.parentElement.id:''):'')))}
const card=document.querySelector('.card');let top='';if(card){const r=card.getBoundingClientRect();const e=document.elementFromPoint(r.left+r.width/2,Math.min(r.top+40,innerHeight-5));top=e?(e.tagName+'#'+e.id+'.'+e.className.toString().slice(0,30)):'none'}return out.concat(['TOPMOST@card: '+top])}"""
with sync_playwright() as p:
    b=p.chromium.launch()
    for pgn in ('system','index'):
        ctx=b.new_context(viewport={'width':1440,'height':900},service_workers='block'); pg=ctx.new_page(); pg.goto('http://localhost:8091/web/%s.html'%pgn,wait_until='load'); pg.wait_for_timeout(5000)
        print('R:',pgn); [print('R:  ',x) for x in pg.evaluate(JS)]; ctx.close()
    b.close()
P
timeout 100 $PY -I /tmp/s3_bg1.py 2>&1 | cut -c1-260
