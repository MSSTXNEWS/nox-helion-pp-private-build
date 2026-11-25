echo "C300: u_ix2"
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright
cat > /tmp/u_ix2.py <<'PEOF'
import asyncio
from playwright.async_api import async_playwright
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch();c=await b.new_page(viewport={'width':1440,'height':900})
    await c.goto('http://127.0.0.1:8091/web/index.html',wait_until='domcontentloaded');await c.wait_for_timeout(7000)
    print(await c.evaluate("""()=>{const o=[];document.querySelectorAll('body *').forEach(e=>{if(e.children.length)return;const t=(e.textContent||'').trim();if(/·\\s*\\d+$/.test(t)&&t.length<40){const s=getComputedStyle(e);const r=e.getBoundingClientRect();o.push(e.tagName+'#'+e.id+'.'+String(e.className).slice(0,30)+' "'+t+'" pos:'+s.position+' '+Math.round(r.left)+','+Math.round(r.top)+' fs'+s.fontSize+' par:'+(e.parentElement?e.parentElement.tagName+'.'+String(e.parentElement.className).slice(0,24):''))}});['?'].forEach(x=>{});const q=[...document.querySelectorAll('button')].filter(e=>(e.textContent||'').trim()==='?').map(e=>e.id+'.'+String(e.className).slice(0,20)+' '+JSON.stringify(e.getBoundingClientRect()).slice(0,80));return o.concat(['Q:'+q.join('|')]).join('\\n')}"""))
    await b.close()
asyncio.run(m())
PEOF
timeout 60 /workspace/nox/venv/bin/python /tmp/u_ix2.py
grep -rln "u-hkb\|· \${" /workspace/nox/web/site/*.js 2>/dev/null | head -3
grep -ln "'ДОБРЫЙ\|\.sec-tag\|section-tag\|data-tag" /workspace/nox/web/site/nox-*.js 2>/dev/null | head -5
cat /workspace/nox/agent/out/u_qab_prog.txt | cut -c1-260
