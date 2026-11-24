cd /workspace/nox/web/site
cat > /tmp/d.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); pg=b.new_page(viewport={'width':1440,'height':900})
    pg.goto('http://localhost:8091/web/downloads.html'); pg.wait_for_timeout(4000)
    print(pg.evaluate("()=>document.getElementById('nxdock').outerHTML.slice(0,3500)"))
    b.close()
P
/workspace/nox/venv/bin/python /tmp/d.py 2>&1 | cut -c1-3600
echo ---; grep -n -i "ninja\|ctrlKey\|metaKey\|palette" nox-shell.js nox-nav.js nox-dock.js nox-dock-wow.js nox-glass.js | cut -c1-220 | head -20
ls vendor | tr '\n' ' '; wc -c nox-shell.js nox-dock.js nox-dock-wow.js
grep -c "nox-dock" downloads.html photo.html
ls /workspace/nox | tr '\n' ' '
