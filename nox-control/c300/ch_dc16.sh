echo "C300: ch_dc16"
S=/workspace/nox/web/site; N=/workspace/nox; cb=$(date +%s); R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ch_dc1
for f in chat-dc.html nox-dc.css nox-dc.js nox-dc-cols.js nox-minichat.js dcqa.py; do curl -fsSL --retry 5 --retry-all-errors "$R/$f?cb=$cb" -o /tmp/dc_$f || { echo FAIL $f; exit 0; }; done
grep -q "dc-ghost" /tmp/dc_nox-dc.js && [ -s /tmp/dc_nox-dc-cols.js ] || { echo STALE; exit 0; }
[ -f $S/nox-minichat.js.bak_ch_dc ] || cp $S/nox-minichat.js $S/nox-minichat.js.bak_ch_dc
cp /tmp/dc_chat-dc.html $S/chat-dc.html; cp /tmp/dc_nox-dc-cols.js $S/nox-dc-cols.js; cp /tmp/dc_nox-dc.css $S/nox-dc.css; cp /tmp/dc_nox-dc.js $S/nox-dc.js; cp /tmp/dc_nox-minichat.js $S/nox-minichat.js
bash <(curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/th_graphite/webroot_sync.sh?cb=$cb") | tail -1
for f in chat-dc.html nox-dc.css nox-dc.js nox-dc-cols.js nox-minichat.js; do cmp $S/$f $N/web/pkg/webroot/$f && echo synced_$f; done
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
cat > /tmp/mini.py <<'PY'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch()
    pg=b.new_page(viewport={'width':390,'height':844},has_touch=True,is_mobile=True)
    pg.goto('http://127.0.0.1:8091/web/settings.html',wait_until='load');pg.wait_for_timeout(4000)
    print('fab',pg.evaluate("(()=>{const f=document.querySelector('.nmc-fab');if(!f)return 'none';const r=f.getBoundingClientRect(),cs=getComputedStyle(f);const t=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return [Math.round(r.x),Math.round(r.y),Math.round(r.width),cs.display,cs.visibility,cs.position,t&&t.className&&String(t.className).slice(0,40)||t&&t.tagName]})()"))
    pg.evaluate("document.querySelector('.nmc-fab').click()");pg.wait_for_timeout(4000)
    print('win',pg.evaluate("(()=>{const w=document.querySelector('.nmc');const r=w.getBoundingClientRect();return [w.hidden,Math.round(r.x),Math.round(r.y),Math.round(r.width),Math.round(r.height)]})()"))
    fr=pg.frames[-1]
    fr.evaluate("document.querySelector('deep-chat').submitUserMessage({text:'привет'})")
    for i in range(60):
        if fr.evaluate("!!document.querySelector('deep-chat').shadowRoot.querySelector('.dc-acts-live')"):break
        pg.wait_for_timeout(1000)
    print('reply390',fr.evaluate("[...document.querySelector('deep-chat').shadowRoot.querySelectorAll('.ai-message-text')].pop().innerText.slice(0,60)"))
PY
timeout 150 $N/venv/bin/python /tmp/mini.py 2>&1 | cut -c1-300 | tail -8
setsid -f bash -c "timeout 900 $N/venv/bin/python /tmp/dc_dcqa.py > $N/agent/out/dcqa.out 2>&1" </dev/null >/dev/null 2>&1; echo qa_started
