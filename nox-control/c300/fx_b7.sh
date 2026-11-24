S=/workspace/nox/web/site
echo ==planets; cat $S/planets.html; echo; echo ==resonance; cat $S/resonance.html; echo ==tv; head -c 1800 $S/tv.html
echo ==stubtail; tail -12 $S/advisors.html | cut -c1-300
echo ==creative; grep -c "id=\"go\"" $S/creative.html
cat > /tmp/chk.py <<'P'
from playwright.sync_api import sync_playwright
import sys
with sync_playwright() as p:
    b=p.chromium.launch(args=['--use-gl=swiftshader','--enable-webgl','--ignore-gpu-blocklist'])
    for n in sys.argv[1].split(','):
        pg=b.new_page(viewport={'width':1440,'height':900}); e=[]
        pg.on('pageerror',lambda x:e.append('PE '+str(x)[:120]))
        pg.on('response',lambda r: e.append('%s %s'%(r.status,r.url[-50:])) if r.status>=400 else None)
        pg.goto('http://127.0.0.1:8091/web/%s.html'%n,wait_until='load'); pg.wait_for_timeout(5000)
        if n=='index': print(pg.inner_text('#svc')[:700])
        print('##',n,e[:8]); pg.close()
    b.close()
P
cd /tmp; /workspace/nox/venv/bin/python /tmp/chk.py index,photo,chat,about,music 2>&1 | head -60
