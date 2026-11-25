#!/bin/bash
grep -n "fav\|recent" /workspace/nox/web/site/nox-dock.js | cut -c1-260 | head -12
cat > /tmp/s3_shot3.py <<'P'
import base64,subprocess,json
from playwright.sync_api import sync_playwright
KEEP={'index_d','dockpop_d','set_models_d','set_personality_d','scene_forge_d','index_m','set_models_m','set_autonomy_m','sheet_m'}
def out(tag,png,w):
    if tag not in KEEP: return
    j='/tmp/s3_%s.jpg'%tag
    subprocess.run(['ffmpeg','-loglevel','error','-y','-i',png,'-vf','scale=%d:-1'%w,'-q:v','14',j])
    b=base64.b64encode(open(j,'rb').read()).decode()
    print('B64_%s_BEGIN'%tag)
    for i in range(0,len(b),900): print(b[i:i+900])
    print('B64_%s_END'%tag)
B='http://localhost:8091/web/'
nav=json.load(open('/workspace/nox/web/site/nav.json'))
files=[i['file'] for g in nav['groups'] for i in g['items']]
print('MENU_FILES',len(files),len(set(files)))
with sync_playwright() as p:
    b=p.chromium.launch()
    import sys
    for tag,w,h,mob in [x for x in [('d',1440,900,0),('m',390,844,1)] if x[0]==sys.argv[1]]:
        ctx=b.new_context(viewport={'width':w,'height':h},has_touch=bool(mob),is_mobile=bool(mob))
        bad=[]
        for f in files:
            pg=ctx.new_page(); errs=[]; st=[]
            pg.on('pageerror',lambda e:errs.append(str(e)[:80])); pg.on('response',lambda r:st.append((r.status,r.url[-40:])) if r.status>=400 else None)
            try:
                pg.goto(B+f,wait_until='load',timeout=20000); pg.wait_for_timeout(900)
                ov=pg.evaluate("document.documentElement.scrollWidth-innerWidth")
                op=pg.evaluate("(()=>{const e=document.querySelector('ninja-keys');return !!(e&&(e.visible||e.hasAttribute('opened')))})()")
                ok=pg.evaluate("[!!document.getElementById('nxsun'),!!document.querySelector('.tb-sun'),document.querySelectorAll('.tb-i[data-k=feel]:not([style*=none])').length]")
                if errs or st or ov>2 or op: bad.append((f,errs[:2],st[:2],ov,op))
            except Exception as e: bad.append((f,'EXC',str(e)[:80]))
            pg.close()
        print('CLICKALL',tag,len(files),'bad',bad)
        pg=ctx.new_page(); pg.goto(B+'index.html',wait_until='load'); pg.wait_for_timeout(3500)
        print('STATE',tag,pg.evaluate("({sun:!!document.getElementById('nxsun'),sunbox:(()=>{const r=document.getElementById('nxsun').getBoundingClientRect();return [r.x|0,r.y|0,r.width|0]})(),ninjaOpen:(()=>{const e=document.querySelector('ninja-keys');return e?[e.visible,e.hasAttribute('opened')]:null})(),world:document.documentElement.dataset.noxWorld,brainIconsHidden:getComputedStyle(document.querySelector('.tb-i[data-k=feel]')).display})"))
        pg.screenshot(path='/tmp/s.png'); out('index_'+tag,'/tmp/s.png',900 if w>800 else 390)
        if not mob:
            pg.hover('#nxdock .nxd-cells a[data-k=chat]'); pg.wait_for_timeout(900); pg.screenshot(path='/tmp/s.png'); out('dockpop_d','/tmp/s.png',900)
            pg.click('#nxsun'); pg.wait_for_timeout(600); pg.screenshot(path='/tmp/s.png'); out('pult_d','/tmp/s.png',900)
            pg.keyboard.press('Escape'); pg.keyboard.press('Control+k'); pg.wait_for_timeout(900); pg.screenshot(path='/tmp/s.png'); out('ninja_d','/tmp/s.png',900)
        else:
            pg.evaluate("NOXNav.openSheet('chat.html')"); pg.wait_for_timeout(900); pg.screenshot(path='/tmp/s.png'); out('sheet_m','/tmp/s.png',390)
        for tab in ['personality','models','autonomy','ui','safety']:
            pg2=ctx.new_page(); pg2.goto(B+'settings.html?tab='+tab,wait_until='load'); pg2.wait_for_timeout(2500)
            if tab in ('models','personality','autonomy'):
                pg2.screenshot(path='/tmp/s.png'); out('set_%s_%s'%(tab,tag),'/tmp/s.png',900 if w>800 else 390)
            pg2.close()
        pg3=ctx.new_page(); pg3.goto(B+'scene.html',wait_until='load'); pg3.wait_for_timeout(2500)
        if not mob:
            pg3.click('#nxworlds [data-w=forge]'); pg3.wait_for_timeout(700); pg3.screenshot(path='/tmp/s.png'); out('scene_forge_d','/tmp/s.png',900)
        ctx.close()
    b.close()
P
for v in d m; do nohup /workspace/nox/venv/bin/python -I /tmp/s3_shot3.py $v > /tmp/s3_shot3_$v.out 2>&1 & done
sleep 5; echo started
