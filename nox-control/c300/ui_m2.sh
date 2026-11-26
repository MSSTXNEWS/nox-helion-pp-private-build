echo "C300: ui_m2"
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python
cat > /tmp/ui_m2.py <<'P'
import asyncio
from playwright.async_api import async_playwright
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch()
    for pg in ('tools','voice','downloads','pdf'):
      c=await b.new_page(viewport={'width':1440,'height':900});await c.goto('http://127.0.0.1:8091/web/'+pg+'.html',wait_until='domcontentloaded');await c.wait_for_timeout(6000)
      print('BTN',pg,await c.evaluate("[...document.querySelectorAll('#app button,#app a,#app sl-button,#app [role=button]')].filter(e=>e.offsetWidth&&!e.closest('#nxdock,header,.tb')&&e.getBoundingClientRect().top<900&&e.getBoundingClientRect().top>60).slice(0,14).map(e=>e.tagName+'#'+e.id+'.'+String(e.className).split(' ')[0]+'|'+(e.textContent||e.getAttribute('aria-label')||'').trim().replace(/\\s+/g,' ').slice(0,22)).join(' ;; ')"),flush=True)
      await c.close()
    # реальные данные: пустые состояния и скелетоны на всех 26 страницах
    for pg in 'index system memory map knowledge widgets projects music news cinema mail calendar settings tools studio photo voice training dispatcher downloads board atlas pdf integrations assistant'.split():
      c=await b.new_page(viewport={'width':1440,'height':900});await c.goto('http://127.0.0.1:8091/web/'+pg+('.html?home=1' if pg=='index' else '.html'),wait_until='domcontentloaded');await c.wait_for_timeout(2500)
      early=await c.evaluate("[document.querySelectorAll('.u-skel').length,document.querySelectorAll('[aria-busy=true]').length]")
      await c.wait_for_timeout(5500)
      late=await c.evaluate("""[document.querySelectorAll('.ds-empty').length,document.querySelectorAll('.u-skel').length,[...document.querySelectorAll('.ds-empty')].slice(0,3).map(e=>(e.closest('section,.card,[id]')||e).id+':'+e.offsetHeight+'x'+e.offsetWidth),[...document.querySelectorAll('body *')].filter(e=>e.children.length===0&&/^(пусто|нет данных|загрузка)[.…\\s]*$/i.test((e.textContent||'').trim())&&e.offsetWidth).length]""")
      print('EMPTY',pg,'early',early,'late',late,flush=True);await c.close()
    await b.close()
asyncio.run(m())
P
timeout 170 $PY /tmp/ui_m2.py
