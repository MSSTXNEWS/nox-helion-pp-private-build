PY=/workspace/nox/venv/bin/python
echo "== DK1"
cat > /tmp/s3_dk1.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={'width':1440,'height':900}); pg.goto('http://localhost:8091/web/index.html',wait_until='load'); pg.wait_for_timeout(3500)
    print('R:', pg.evaluate("()=>[...document.querySelectorAll('body *')].filter(e=>{const s=getComputedStyle(e);const r=e.getBoundingClientRect();return s.position=='fixed'&&r.height>10&&r.width>40}).map(e=>(e.id?'#'+e.id:'')+'.'+e.className.toString().slice(0,30)+' top'+Math.round(e.getBoundingClientRect().top)+' h'+Math.round(e.getBoundingClientRect().height)+' kids['+[...e.children].map(c=>(c.id?'#'+c.id:'')+'.'+c.className.toString().slice(0,18)).join(',').slice(0,160)+']').join('\\n')"))
    print('R:', pg.evaluate("()=>[...document.querySelectorAll('#nxdock *, #nxpult *')].filter(e=>e.children.length==0&&e.textContent.trim()).slice(0,40).map(e=>e.tagName+'.'+e.className.toString().slice(0,14)+'='+e.textContent.trim().slice(0,14)).join(' | ')"))
    b.close()
P
timeout 100 $PY -I /tmp/s3_dk1.py 2>&1 | cut -c1-900
