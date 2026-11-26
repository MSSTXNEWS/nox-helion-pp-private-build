echo "C300: w_b13"
N=/workspace/nox; export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
cat > /tmp/d3.py <<'P'
from playwright.sync_api import sync_playwright
from PIL import Image, ImageChops
W="""(l)=>{function wn(e,t){var n=document.createElement('nav');n.style.display='contents';e.parentNode.insertBefore(n,e);n.appendChild(e)}
 if(l.includes('H'))[...document.querySelectorAll('body > header')].forEach(e=>{if(e.id!=='noxSharedHeaderV10')wn(e)});
 if(l.includes('S'))[...document.querySelectorAll('body > .helion-skip')].forEach(wn);
 if(l.includes('C')){var s=document.createElement('style');s.textContent='.nox-shared-signature-v10,#nox-cinematic-light-cycle,.nox-graphic-control{min-height:45px!important;min-width:44px!important}';document.head.appendChild(s)}}"""
def diff(a,b):
    a=Image.open(a).convert('L');b=Image.open(b).convert('L');d=ImageChops.difference(a,b).point(lambda v:255 if v>40 else 0);return round(sum(1 for v in d.getdata() if v)/(a.size[0]*a.size[1])*100,2)
with sync_playwright() as p:
    b=p.chromium.launch(args=['--use-gl=swiftshader','--use-angle=swiftshader','--enable-unsafe-swiftshader','--no-sandbox'])
    for w,h in ((1440,900),(390,844)):
        for v in ('','H','S','C','HSC'):
            pg=b.new_page(viewport={'width':w,'height':h});pg.goto('http://127.0.0.1:18091/web/index.html?ixfix=0',wait_until='load',timeout=60000);pg.wait_for_timeout(3000)
            pg.evaluate(W,v);pg.wait_for_timeout(2500);pg.screenshot(path='/tmp/v_%d_%s.png'%(w,v or 'base'));pg.close()
        print(w,{v:diff('/tmp/n_%d_1.png'%w,'/tmp/v_%d_%s.png'%(w,v or 'base')) for v in ('','H','S','C','HSC')} if False else {v:diff('/tmp/v_%d_base.png'%w,'/tmp/v_%d_%s.png'%(w,v)) for v in ('H','S','C','HSC')})
    b.close()
P
timeout 200 $N/venv/bin/python -W ignore /tmp/d3.py 2>&1 | cut -c1-600
