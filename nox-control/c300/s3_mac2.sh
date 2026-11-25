#!/bin/bash
S=/workspace/nox/web/site
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
cd $S
curl -fsSL "$RAW/nox-planets3d.js?v=$(date +%s)" -o /tmp/s3m2.js && cp /tmp/s3m2.js $S/nox-planets3d.js && echo placed planets3d
/workspace/nox/venv/bin/python /workspace/nox/qa_ctl.py --pin
cat > /tmp/s3_mac2_shot.py <<'P'
import base64,subprocess
from playwright.sync_api import sync_playwright
def out(tag,png,w):
    j='/tmp/s3m2_%s.jpg'%tag
    subprocess.run(['ffmpeg','-loglevel','error','-y','-i',png,'-vf','scale=%d:-1'%w,'-q:v','14',j])
    b=base64.b64encode(open(j,'rb').read()).decode()
    print('B64_%s_BEGIN'%tag)
    for i in range(0,len(b),900): print(b[i:i+900])
    print('B64_%s_END'%tag)
B='http://localhost:8091/web/'
with sync_playwright() as p:
    b=p.chromium.launch(args=['--use-gl=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist'])
    for tag,w,h,mob in [('d',1440,900,0),('m',390,844,1)]:
        ctx=b.new_context(viewport={'width':w,'height':h},has_touch=bool(mob),is_mobile=bool(mob))
        for name,url in [('models','settings.html?tab=models'),('scene','scene.html')]:
            pg=ctx.new_page(); errs=[]; pg.on('pageerror',lambda e:errs.append(str(e)[:120])); pg.on('console',lambda m:errs.append('C:'+m.text[:100]) if m.type=='error' else None)
            pg.goto(B+url,wait_until='load'); pg.wait_for_timeout(9000)
            info=pg.evaluate("({tiles:document.querySelectorAll('.nxpl-g button').length,sw:document.querySelectorAll('sl-switch').length,rg:document.querySelectorAll('sl-radio-group').length,over:document.documentElement.scrollWidth-innerWidth,note:(document.querySelector('.nxpl-n')||{}).textContent})")
            print('INFO',tag,name,info,errs[:4])
            if name=='ui' and not mob:
                pg.click('.nxpl-g [data-id=mars]'); pg.wait_for_timeout(1500); print('PLANET',pg.evaluate("localStorage.getItem('nox:planet')"))
            pg.screenshot(path='/tmp/s.png'); out('%s_%s'%(name,tag),'/tmp/s.png',900 if w>800 else 390)
            pg.close()
        ctx.close()
    b.close()
P
nohup /workspace/nox/venv/bin/python -I /tmp/s3_mac2_shot.py > /tmp/s3_mac2_shot.out 2>&1 &
for i in $(seq 1 3); do pgrep -f s3_mac2_shot.py >/dev/null || break; sleep 10; done
cut -c1-900 /tmp/s3_mac2_shot.out
