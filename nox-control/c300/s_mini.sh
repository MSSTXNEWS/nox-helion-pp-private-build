cd /tmp
cat > /tmp/shot_mini.py <<'P'
import base64,subprocess,sys
from playwright.sync_api import sync_playwright
def out(tag,png,w):
    j='/tmp/s_%s.jpg'%tag
    subprocess.run(['ffmpeg','-loglevel','error','-y','-i',png,'-vf','scale=%d:-1'%w,'-q:v','11',j])
    b=base64.b64encode(open(j,'rb').read()).decode()
    print('B64_%s_BEGIN'%tag)
    for i in range(0,len(b),900): print(b[i:i+900])
    print('B64_%s_END'%tag)
with sync_playwright() as p:
    b=p.chromium.launch()
    for mob in (0,1):
        pg=b.new_page(viewport={'width':390,'height':844} if mob else {'width':1440,'height':900}, has_touch=bool(mob), is_mobile=bool(mob))
        errs=[]; pg.on('pageerror',lambda e:errs.append(str(e)[:120]))
        pg.goto('http://localhost:8091/web/index.html',wait_until='load'); pg.wait_for_timeout(5000)
        if mob:
            pg.click('.nmc-fab'); pg.fill('.nmc textarea','Привет'); pg.keyboard.press('Enter'); pg.wait_for_timeout(15000)
        else:
            pg.click('.nmc-fab'); pg.fill('.nmc textarea','Привет, где я?'); pg.keyboard.press('Enter'); pg.wait_for_timeout(15000)
        pg.wait_for_timeout(1200)
        pg.screenshot(path='/tmp/s.png')
        out('mini_'+('m' if mob else 'd'),'/tmp/s.png',760 if not mob else 390)
        print('ERRS',errs[:3])
    b.close()
P
/workspace/nox/venv/bin/python /tmp/shot_mini.py 2>&1 | cut -c1-900
