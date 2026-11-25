PY=/workspace/nox/venv/bin/python
echo "== TR1"
cat > /tmp/s3_tr1.py <<'P'
import base64,subprocess
from playwright.sync_api import sync_playwright
JS="""()=>{const o=[];for(const c of document.querySelectorAll('canvas')){if(c.id=='space'||c.closest('#dust,#nox-fx-ash'))continue;const r=c.getBoundingClientRect();let p=c,chain=[];while(p&&p!==document.body){const s=getComputedStyle(p);chain.push(p.tagName+'.'+p.className.toString().slice(0,14)+'['+s.position+',z'+s.zIndex+']');p=p.parentElement}const card=c.closest('.card');o.push({size:Math.round(r.width)+'x'+Math.round(r.height),top:Math.round(r.top),card:card?getComputedStyle(card).backgroundColor:'NO CARD',chain:chain.slice(0,4).join('>')})}return o.slice(0,8)}"""
with sync_playwright() as p:
    b=p.chromium.launch(); ctx=b.new_context(viewport={'width':1440,'height':900},service_workers='block'); pg=ctx.new_page(); pg.goto('http://localhost:8091/web/training.html',wait_until='load'); pg.wait_for_timeout(5500)
    for x in pg.evaluate(JS): print('R:',x)
    print('R: cards', pg.evaluate("()=>[...document.querySelectorAll('.card')].slice(0,8).map(c=>c.className.toString().slice(0,30)+' bg='+getComputedStyle(c).backgroundColor+' bf='+getComputedStyle(c).backdropFilter.slice(0,12)+' h='+Math.round(c.getBoundingClientRect().height)).join(' | ')"))
    pg.screenshot(path='/tmp/s.png'); subprocess.run(['ffmpeg','-loglevel','error','-y','-i','/tmp/s.png','-vf','scale=1000:-1','-q:v','8','/tmp/s.jpg'])
    print('B64_BEGIN'); print(base64.b64encode(open('/tmp/s.jpg','rb').read()).decode()); print('B64_END'); b.close()
P
timeout 100 $PY -I /tmp/s3_tr1.py 2>&1 | fold -w 900
