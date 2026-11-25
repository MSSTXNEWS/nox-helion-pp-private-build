echo "C300: u_rec2"
S=/workspace/nox/web/site; cd $S
echo "== caddy"; ps aux | grep -i "[c]addy" | cut -c1-200 | head -3; ls /workspace/nox/web/*/Caddyfile /workspace/nox/*/Caddyfile /etc/caddy/Caddyfile 2>/dev/null
for f in $(ls /workspace/nox/web/*/Caddyfile /workspace/nox/*/Caddyfile /etc/caddy/Caddyfile 2>/dev/null | head -2); do echo "-- $f"; cat $f | head -60; done
ss -ltn | grep -E ":(18091|8080|8091)\b"
echo "== ext access test (no auth) on 8080/18091"
for p in 8080 18091; do for u in /svc/advgw/health /svc/agentsb/board /web/index.html; do echo "$p $u $(curl -s -m 5 -o /dev/null -w '%{http_code}' localhost:$p$u)"; done; done
echo "== auth in web_server"; grep -n "nox_web_chat_auth\|X-Forwarded\|auth" /workspace/nox/web/pkg/server/web_server.py | cut -c1-160 | head -12
echo "== qa_audit"; ls /workspace/nox/web/*/qa_audit.py /workspace/nox/*/qa_audit.py $S/qa_audit.py 2>/dev/null; find /workspace/nox -name qa_audit.py -maxdepth 4 2>/dev/null | head -3
echo "== chat5"; ls $S | grep -i "chat-5\|chat5"; grep -n "tgWid\|col5\|widget" $S/nox-chat-5.js 2>/dev/null | cut -c1-200 | head -15
echo "== finance fab"; cat > /tmp/u_f.py <<'PEOF'
import asyncio
from playwright.async_api import async_playwright
async def m():
  async with async_playwright() as p:
    b=await p.chromium.launch();c=await b.new_page(viewport={'width':1440,'height':900})
    await c.goto('http://127.0.0.1:8091/web/finance.html',wait_until='domcontentloaded');await c.wait_for_timeout(4000)
    print(await c.evaluate("""()=>{const f=document.querySelector('.nmc-fab');const b=f.getBoundingClientRect();const o=[];for(const [dx,dy] of [[0,0],[-15,-15],[15,15]]){const t=document.elementFromPoint(b.left+b.width/2+dx,b.top+b.height/2+dy);o.push(t?t.tagName+'#'+t.id+'.'+String(t.className).slice(0,30)+' p:'+(t.closest('[id]')||{}).id:null)}return [b.left|0,b.top|0,b.width|0,b.height|0,getComputedStyle(f).bottom,o]}"""))
    await b.close()
asyncio.run(m())
PEOF
PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright timeout 60 /workspace/nox/venv/bin/python /tmp/u_f.py
grep -o "k8-budget[^{]*{[^}]*}" nox-k8-ui.css | head -5 | cut -c1-200; grep -n "button" nox-k8-budget.js | head -5 | cut -c1-200
echo done
