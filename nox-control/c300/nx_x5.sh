cat > /tmp/q.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={'width':1440,'height':900})
    pg.goto('http://localhost:8091/web/events.html'); pg.wait_for_timeout(4500)
    print(pg.evaluate("""()=>{const w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let n,o=[];while(n=w.nextNode()){if(n.textContent.includes('Напиши на Python')){let e=n.parentElement,c=[];while(e&&e!==document.body){c.push(e.tagName+'#'+e.id+'.'+e.className+'['+getComputedStyle(e).position+','+getComputedStyle(e).display+','+e.hidden+']');e=e.parentElement}o.push(c.join(' < '))}}return o.join('\\n')}"""))
    b.close()
P
/workspace/nox/venv/bin/python /tmp/q.py | cut -c1-900
grep -c "miniPan" /workspace/nox/web/site/nox-dock.js; grep -n "mini-pan" /workspace/nox/web/site/*.css | head -5 | cut -c1-200
