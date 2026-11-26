echo "C300: w_t4"
N=/workspace/nox; S=$N/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
ok=0; for k in 1 2 3 4 5 6 7 8; do t=$(date +%s)$k
 curl -fsSL "$R/w_roles/nox-roles-x2.js?cb=$t" -o /tmp/x2.js; curl -fsSL "$R/w_msgr/nox-messenger-dc.js?cb=$t" -o /tmp/msgr.js
 grep -q 'my !== tok' /tmp/x2.js && grep -q 'nxMsgr' /tmp/msgr.js && { ok=1; break; }; sleep 15; done
[ $ok = 1 ] || { echo STALE; exit 0; }
cp /tmp/x2.js $S/nox-roles-x2.js; cp /tmp/msgr.js $S/nox-messenger-dc.js
python3 - <<'P'
S='/workspace/nox/web/site/'
c=open(S+'messenger.html').read()
if 'nox-messenger-dc.js' not in c:
    k='<script src="./nox-radial.js" defer></script>'; assert k in c
    open(S+'messenger.html.bak_w_t2','w').write(c); open(S+'messenger.html','w').write(c.replace(k,'<script src="./nox-messenger-dc.js" defer></script>\n'+k,1)); print('messenger patched')
P
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$(date +%s)") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$(date +%s)") | tail -1
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
cat > /tmp/t2.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(args=['--use-gl=swiftshader','--use-angle=swiftshader','--enable-unsafe-swiftshader','--no-sandbox'])
    pg=b.new_page(viewport={'width':1440,'height':900});errs=[];pg.on('pageerror',lambda e:errs.append(str(e)[:100]))
    pg.goto('http://127.0.0.1:18091/web/messenger.html',wait_until='load');pg.wait_for_timeout(5000)
    print('msgr',pg.evaluate("[!!document.querySelector('#nxMsgr deep-chat'),document.querySelectorAll('#nxmTabs button').length]"),errs)
    pg.goto('http://127.0.0.1:18091/web/calls.html',wait_until='load');pg.wait_for_timeout(3500)
    pg.evaluate("document.getElementById('nxjNew').click()");pg.wait_for_timeout(9000)
    print('jitsi frames',pg.evaluate("[document.querySelectorAll('iframe').length,[...document.querySelectorAll('iframe')].map(f=>f.src.slice(0,60))]"),pg.evaluate("typeof window.JitsiMeetExternalAPI"))
    pg.goto('http://127.0.0.1:18091/web/writer.html?role=scientist',wait_until='load');pg.wait_for_timeout(4500)
    for s in ('semantic','crossref'):
        pg.evaluate("s=>{document.querySelector('.rx2-t[data-s='+s+']').click();const q=document.getElementById('rx2-q');q.value='entropy';document.getElementById('rx2-go').click()}",s);pg.wait_for_timeout(9000)
        print(s,pg.evaluate("[document.getElementById('rx2-ss').textContent,document.querySelectorAll('#rx2-res sl-card').length]"))
    b.close()
P
timeout 150 $N/venv/bin/python /tmp/t2.py 2>&1 | cut -c1-300

N=/workspace/nox; S=$N/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
ok=0; for k in 1 2 3 4 5 6 7 8; do t=$(date +%s)$k
 curl -fsSL "$R/ch_dc1/nox-dc-live.js?cb=$t" -o /tmp/live.js; curl -fsSL "$R/w_bridge/api_bridge.py?cb=$t" -o /tmp/br.py
 grep -q 'self_now' /tmp/live.js && grep -q 'api/nox/briefs' /tmp/br.py && { ok=1; break; }; sleep 15; done
[ $ok = 1 ] || { echo STALE; exit 0; }
python3 -c "import ast;ast.parse(open('/tmp/br.py').read())" || exit 0
B=$(ls $N/*/api_bridge.py $N/ops/*/api_bridge.py 2>/dev/null | head -1); echo "bridge=$B"
[ -n "$B" ] && { cp $B $B.bak_t3; cp /tmp/br.py $B; supervisorctl restart nox_api_bridge | tail -1; }
cp /tmp/live.js $S/nox-dc-live.js
python3 - <<'P'
S='/workspace/nox/web/site/'
c=open(S+'chat-dc.html').read()
if 'nox-dc-live.js' not in c:
    k='<script src="./nox-dc-draw.js'; assert k in c
    open(S+'chat-dc.html.bak_w_t3','w').write(c); open(S+'chat-dc.html','w').write(c.replace(k,'<script src="./nox-dc-live.js?v=l1" defer></script>\n'+k,1)); print('chat patched')
P
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$(date +%s)") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$(date +%s)") | tail -1
sleep 3
for u in self_now briefs; do curl -s http://127.0.0.1:8796/api/nox/$u | python3 -c "import sys,json;d=json.load(sys.stdin);print('$u ok',d.get('ok'),'hold',d.get('hold'),sorted(k for k in d if k!='data')[:6])"; done
