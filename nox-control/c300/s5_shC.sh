ls /workspace/nox/web/site/qa/rework/*.fixed 2>/dev/null
cat > /tmp/s5shot.py <<'P'
import base64,subprocess,sys,json
from playwright.sync_api import sync_playwright
def out(tag,png,w):
    j='/tmp/s5_%s.jpg'%tag
    subprocess.run(['ffmpeg','-loglevel','error','-y','-i',png,'-vf','scale=%d:-1'%w,'-q:v','9',j])
    b=base64.b64encode(open(j,'rb').read()).decode()
    print('B64_%s_BEGIN'%tag)
    for i in range(0,len(b),900): print(b[i:i+900])
    print('B64_%s_END'%tag)
with sync_playwright() as p:
    b=p.chromium.launch(args=['--use-gl=swiftshader','--enable-webgl','--ignore-gpu-blocklist'])
    for name in sys.argv[1:]:
        for mob in (0,1):
            pg=b.new_page(viewport={'width':390,'height':844} if mob else {'width':1440,'height':900}, has_touch=bool(mob), is_mobile=bool(mob))
            errs=[];bad=[]
            pg.on('pageerror',lambda e:errs.append(str(e)[:100])); pg.on('response',lambda r:bad.append(str(r.status)+r.url[-40:]) if r.status>=400 else None)
            try:
                pg.goto('http://localhost:8091/web/'+name+'.html',wait_until='load',timeout=30000); pg.wait_for_timeout(5000)
                info=pg.evaluate("()=>({cmd:typeof window.NOXcmd,btn:document.querySelectorAll('button').length,hs:document.documentElement.scrollWidth>innerWidth+1,vend:[...document.scripts].map(s=>s.src).filter(s=>/vendor/.test(s)).length})")
                pg.screenshot(path='/tmp/s5.png'); out(name+('_m' if mob else '_d'),'/tmp/s5.png',390 if mob else 800)
                print('INFO',name,mob,json.dumps(info),'ERR',errs[:3],'BAD',bad[:3])
            except Exception as e: print('FAIL',name,str(e)[:100])
            pg.close()
    b.close()
P
/workspace/nox/venv/bin/python /tmp/s5shot.py consciousness organism soul growth 2>&1 | cut -c1-900
find /workspace/nox -iname "VENDOR_INDEX*" 2>/dev/null | head -3
f=$(find /workspace/nox -iname "VENDOR_INDEX.md" 2>/dev/null | head -1); [ -n "$f" ] && head -60 "$f" | cut -c1-200
