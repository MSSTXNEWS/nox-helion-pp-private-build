S=/workspace/nox/web/site
echo ==photo; sed -n 16,70p $S/photo.html | cut -c1-260
echo ==about body; sed -n 17,34p $S/about.html | cut -c1-300
cat > /tmp/dom.py <<'P'
from playwright.sync_api import sync_playwright
import sys,json
with sync_playwright() as p:
    b=p.chromium.launch(args=['--use-gl=swiftshader','--enable-webgl','--ignore-gpu-blocklist'])
    for n in sys.argv[1].split(','):
        pg=b.new_page(viewport={'width':1440,'height':900}); errs=[]
        pg.on('console',lambda m: errs.append(m.text[:100]) if m.type in('error','warning') else None)
        pg.on('response',lambda r: errs.append('%s %s'%(r.status,r.url[-60:])) if r.status>=400 else None)
        pg.goto('http://127.0.0.1:8091/web/%s.html'%n,wait_until='load'); pg.wait_for_timeout(5000)
        r=pg.evaluate("""()=>[...document.querySelectorAll('body *')].filter(e=>{const s=getComputedStyle(e);return (s.position==='fixed'||s.position==='sticky')}).map(e=>{const b=e.getBoundingClientRect();return e.tagName+'#'+e.id+'.'+String(e.className).slice(0,30)+' '+Math.round(b.left)+','+Math.round(b.top)+' '+Math.round(b.width)+'x'+Math.round(b.height)}).slice(0,40)""")
        print('##',n); print('\n'.join(r)); print(errs[:12])
        pg.close()
    b.close()
P
cd /tmp; /workspace/nox/venv/bin/python /tmp/dom.py photo,about,chat 2>&1
echo ==srv
grep -rl "8091" /workspace/nox --include=*.py --include=*.service --include=*.sh --include=Caddyfile -s 2>/dev/null | head; ls /workspace/nox | head -50
ls /etc/supervisor/conf.d 2>/dev/null; ls /opt 2>/dev/null
