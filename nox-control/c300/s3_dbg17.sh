S=/workspace/nox/web/site; PY=/workspace/nox/venv/bin/python
echo "== DBG17"; grep -n -i "pdf\|документ\|editor" $S/nav.json | cut -c1-200 | head
grep -n "boot\|io0" $S/nox-planets3d.js | cut -c1-200
cat > /tmp/s3_dbg17.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(); ctx=b.new_context(viewport={'width':1440,'height':900},service_workers='block'); pg=ctx.new_page()
    pg.on('pageerror',lambda e: print('R: pageerror',str(e)[:200])); pg.on('console',lambda m: print('R: console',m.type,m.text[:160]) if m.type=='error' else None)
    pg.goto('http://localhost:8091/web/settings.html',wait_until='load'); pg.wait_for_timeout(3000)
    pg.evaluate("()=>[...document.querySelectorAll('.nxm-side [role=tab]')].find(b=>/Интерфейс/.test(b.textContent)).click()"); pg.wait_for_timeout(1500)
    print('R:', pg.evaluate("()=>{const e=document.querySelector('.nxpl');if(!e)return 'no nxpl';const r=e.getBoundingClientRect();const s=e.closest('section');return [Math.round(r.top),Math.round(r.height),s&&s.className,getComputedStyle(e).display]}"))
    pg.evaluate("()=>{const e=document.querySelector('.nxpl');e&&e.scrollIntoView({block:'center'})}"); pg.wait_for_timeout(4000)
    print('R2:', pg.evaluate("()=>[document.querySelector('.nxpl-g').children.length,(document.querySelector('.nxpl-n')||{}).textContent]"))
    b.close()
P
timeout 100 $PY -I /tmp/s3_dbg17.py 2>&1 | cut -c1-300
