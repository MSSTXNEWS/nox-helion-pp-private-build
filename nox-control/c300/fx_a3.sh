S=/workspace/nox/web/site
echo ==theme; cat $S/nox-theme.js; echo; echo ==nav; cat $S/nox-nav.js | head -c 5600
echo; echo ==qa_ctl; sed -n 15,35p /workspace/nox/qa_ctl.py
echo ==srv; ls -la /proc/2575056/cwd; cat /proc/2575056/cmdline | tr '\0' ' '; echo
cat > /tmp/shot_fx.py <<'P'
import base64,subprocess,sys
from playwright.sync_api import sync_playwright
pages=sys.argv[1].split(',')
def out(tag,png,w):
    j='/tmp/s_%s.jpg'%tag
    subprocess.run(['ffmpeg','-loglevel','error','-y','-i',png,'-vf','scale=%d:-1'%w,'-q:v','11',j])
    b=base64.b64encode(open(j,'rb').read()).decode()
    print('B64_%s_BEGIN'%tag)
    for i in range(0,len(b),900): print(b[i:i+900])
    print('B64_%s_END'%tag)
with sync_playwright() as p:
    b=p.chromium.launch(args=['--use-gl=swiftshader','--enable-webgl','--ignore-gpu-blocklist'])
    for pgn in pages:
      for mob in (0,1):
        pg=b.new_page(viewport={'width':390,'height':844} if mob else {'width':1440,'height':900}, has_touch=bool(mob), is_mobile=bool(mob))
        pg.goto('http://127.0.0.1:8091/web/%s.html'%pgn,wait_until='load'); pg.wait_for_timeout(6000)
        pg.screenshot(path='/tmp/s.png')
        out('%s_%s'%(pgn,'m' if mob else 'd'),'/tmp/s.png',390 if mob else 640)
        pg.close()
    b.close()
P
cd /tmp; /workspace/nox/venv/bin/python /tmp/shot_fx.py photo,advisors,about 2>&1 | tail -n +1
