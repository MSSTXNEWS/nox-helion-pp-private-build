#!/bin/bash
cat > /tmp/s3_shot5.py <<'P'
import base64,subprocess
from playwright.sync_api import sync_playwright
def out(tag,png,w):
    j='/tmp/s3_5_%s.jpg'%tag
    subprocess.run(['ffmpeg','-loglevel','error','-y','-i',png,'-vf','scale=%d:-1'%w,'-q:v','14',j])
    b=base64.b64encode(open(j,'rb').read()).decode()
    print('B64_%s_BEGIN'%tag)
    for i in range(0,len(b),900): print(b[i:i+900])
    print('B64_%s_END'%tag)
B='http://localhost:8091/web/'
with sync_playwright() as p:
    b=p.chromium.launch(args=['--use-gl=swiftshader','--enable-unsafe-swiftshader','--ignore-gpu-blocklist'])
    for tag,w,h,mob,sc in [('d',1440,900,0,1),('m',390,844,1,2),('k',3840,2160,0,1)]:
        ctx=b.new_context(viewport={'width':w,'height':h},has_touch=bool(mob),is_mobile=bool(mob),device_scale_factor=1)
        for name,url in [('set','settings.html?tab=ui'),('scene','scene.html')]:
            pg=ctx.new_page(); errs=[]; pg.on('pageerror',lambda e:errs.append(str(e)[:100]))
            pg.goto(B+url,wait_until='load'); pg.wait_for_timeout(11000)
            info=pg.evaluate("({tiles:document.querySelectorAll('.nxpl-g button').length,note:(document.querySelector('.nxpl-n')||{}).textContent,over:document.documentElement.scrollWidth-innerWidth})")
            print('INFO',tag,name,info,errs[:3])
            pg.screenshot(path='/tmp/s.png'); out('%s_%s'%(name,tag),'/tmp/s.png',1000 if w>800 else 390); pg.close()
        if tag=='d':
            pg=ctx.new_page(); pg.goto(B+'index.html',wait_until='load'); pg.wait_for_timeout(3500)
            r=pg.evaluate("(()=>{const r=document.getElementById('nxsun').getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/2]})()")
            pg.mouse.move(r[0],r[1]); pg.mouse.down(); pg.wait_for_timeout(900); pg.screenshot(path='/tmp/s.png'); out('radial_d','/tmp/s.png',700); pg.mouse.up()
        ctx.close()
    b.close()
P
nohup /workspace/nox/venv/bin/python -I /tmp/s3_shot5.py > /tmp/s3_shot5.out 2>&1 &
for i in $(seq 1 26); do pgrep -f s3_shot5.py >/dev/null || break; sleep 10; done
cut -c1-900 /tmp/s3_shot5.out | head -c 60000
