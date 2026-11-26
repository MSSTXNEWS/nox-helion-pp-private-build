echo "C300: w_r1"
N=/workspace/nox; S=$N/web/site; export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
echo "pages with worlds engine:"; grep -l "nox-cinematic-worlds" $S/*.html | xargs -n1 basename | tr '\n' ' '; echo
ls -la $S/studio.html | cut -c20-80
grep -o 'data-nox-[a-z-]*' $S/studio.html | sort | uniq -c | sort -rn | head -12
grep -o 'localStorage.setItem([^)]*)' $S/studio.html | sort | uniq -c | sort -rn | head -12
grep -o -i 'material[a-zA-Z-]*' $S/studio.html | sort | uniq -c | sort -rn | head -8
cat > /tmp/r1.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(args=['--use-gl=swiftshader','--use-angle=swiftshader','--enable-unsafe-swiftshader','--no-sandbox'])
    for n in ('studio','settings','system','chat-dc'):
        pg=b.new_page(viewport={'width':1920,'height':1080});pg.goto('http://127.0.0.1:18091/web/%s.html'%n,wait_until='load',timeout=60000);pg.wait_for_timeout(5000)
        print(n,pg.evaluate("""()=>({eng:!!window.NOX_CINEMATIC_WORLDS,st:window.NOX_CINEMATIC_WORLDS&&NOX_CINEMATIC_WORLDS.getState(),html:[...document.documentElement.attributes].map(a=>a.name+'='+a.value.slice(0,20)).join(' ').slice(0,300),body:[...document.body.attributes].map(a=>a.name+'='+a.value.slice(0,20)).join(' ').slice(0,200),ls:Object.keys(localStorage).filter(k=>/world|pal|mater|finish|button|theme|nox\\.(fx|cin)/i.test(k)).map(k=>k+'='+localStorage[k].slice(0,30))})"""))
        pg.close()
    b.close()
P
timeout 120 $N/venv/bin/python /tmp/r1.py 2>&1 | cut -c1-900
