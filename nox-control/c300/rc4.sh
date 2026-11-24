cd /workspace/nox/web/site
cat studio.html | head -c 2000; echo; echo ---
cat > /tmp/d.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={'width':1440,'height':900})
    pg.goto('http://localhost:8091/web/downloads.html'); pg.wait_for_timeout(4000)
    print(pg.evaluate("""()=>{const o=[];document.querySelectorAll('body *').forEach(e=>{const s=getComputedStyle(e);if(s.position==='fixed'&&e.id!=='space'&&e.id!=='dust'&&!/grain|vignette/.test(e.className))o.push(e.tagName+'#'+e.id+'.'+e.className+' '+JSON.stringify(e.getBoundingClientRect()))});return o.join('\\n')}"""))
    h=pg.evaluate("()=>{const d=document.querySelector('.dock,.bar,#dock,nav');return d?d.outerHTML.slice(0,2500):'none'}")
    print(h)
    b.close()
P
/workspace/nox/venv/bin/python /tmp/d.py 2>&1 | cut -c1-2600
