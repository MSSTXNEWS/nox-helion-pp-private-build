echo "C300: w_t1"
N=/workspace/nox; S=$N/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
ok=0; for k in 1 2 3 4 5 6 7 8; do t=$(date +%s)$k
 curl -fsSL "$R/ch_dc1/nox-dc-draw.js?cb=$t" -o /tmp/draw.js; curl -fsSL "$R/w_roles/nox-roles-x2.js?cb=$t" -o /tmp/x2.js; curl -fsSL "$R/w_calls/nox-calls-jitsi.js?cb=$t" -o /tmp/jit.js; curl -fsSL "$R/w_bridge/api_bridge.py?cb=$t" -o /tmp/api_bridge.py
 grep -q 'disabled|отключ' /tmp/draw.js && grep -q 'Источники ищутся панелью' /tmp/x2.js && grep -q 'external_api' /tmp/jit.js && grep -q 'sci_arxiv' /tmp/api_bridge.py && { ok=1; break; }; sleep 15; done
[ $ok = 1 ] || { echo STALE; exit 0; }
cp /tmp/draw.js $S/nox-dc-draw.js; sed -i 's#nox-dc-draw.js?v=dr2#nox-dc-draw.js?v=dr3#' $S/chat-dc.html
cp /tmp/x2.js $S/nox-roles-x2.js; cp /tmp/jit.js $S/nox-calls-jitsi.js
python3 - <<'P'
S='/workspace/nox/web/site/'
w=open(S+'writer.html').read()
if 'nox-roles-x2.js' not in w:
    k='<script src="./nox-roles-x.js?v=1" defer></script>'; assert k in w
    open(S+'writer.html.bak_w_t1','w').write(w); open(S+'writer.html','w').write(w.replace(k,k+'<script src="./nox-roles-x2.js?v=1" defer></script>',1)); print('writer patched')
c=open(S+'calls.html').read()
if 'nox-calls-jitsi.js' not in c:
    k='<script src="./nox-radial.js" defer></script>'; assert k in c
    open(S+'calls.html.bak_w_t1','w').write(c); open(S+'calls.html','w').write(c.replace(k,'<script src="./nox-calls-jitsi.js" defer></script>\n'+k,1)); print('calls patched')
P
D=$N/ops/api_bridge; cp $D/api_bridge.py $D/api_bridge.py.bak_t1; cp /tmp/api_bridge.py $D/api_bridge.py
supervisorctl restart nox_api_bridge | tail -1; sleep 3
CF=$N/ops/web_chat_auth/Caddyfile
if ! grep -q 'handle /api/sci/\*' $CF; then
 cp $CF $CF.bak_t1_$(date +%s)
 PORT=$(grep -o 'BRIDGE_PORT="[0-9]*"' /etc/supervisor/conf.d/nox_api_bridge.conf | grep -o '[0-9]*')
 python3 - $CF $PORT <<'P'
import sys
f,port=sys.argv[1],sys.argv[2]
s=open(f).read(); k="\thandle /api/notifications {"; assert k in s
s=s.replace(k,"\thandle /api/sci/* {\n\t\treverse_proxy 127.0.0.1:%s\n\t}\n"%port+k,1); open(f,'w').write(s); print('caddy inserted')
P
 export HOME=$N/ops/web_chat_auth XDG_CONFIG_HOME=$N/ops/web_chat_auth/xdg XDG_DATA_HOME=$N/ops/web_chat_auth/xdg-data
 if /opt/instance-tools/bin/caddy validate --config $CF --adapter caddyfile 2>&1 | tail -2 | grep -qi valid; then supervisorctl restart nox_web_chat_auth | tail -1; sleep 6; ps -eo pid,cmd | grep -c '[w]eb_chat_auth/Caddyfile'
 else echo VALIDATE_FAIL; ls -t $CF.bak_t1_* | head -1 | xargs -I{} cp {} $CF; fi
fi
echo -n "arxiv via 18091: "; curl -s -m15 'http://127.0.0.1:18091/api/sci/arxiv?q=entropy' | head -c 200; echo
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$(date +%s)") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$(date +%s)") | tail -1
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
cat > /tmp/t1.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(args=['--use-gl=swiftshader','--use-angle=swiftshader','--enable-unsafe-swiftshader','--no-sandbox'])
    pg=b.new_page(viewport={'width':1440,'height':900});errs=[];pg.on('pageerror',lambda e:errs.append(str(e)[:100]))
    pg.goto('http://127.0.0.1:18091/web/writer.html?role=scientist',wait_until='load');pg.wait_for_timeout(5000)
    print('panel',pg.evaluate("!!document.getElementById('rx2')"),errs)
    for s in ('openalex','semantic','crossref','arxiv','wiki'):
        pg.evaluate("s=>{document.querySelector('.rx2-t[data-s='+s+']').click();const q=document.getElementById('rx2-q');q.value='entropy';document.getElementById('rx2-go').click()}",s);pg.wait_for_timeout(7000)
        print(s,pg.evaluate("[document.getElementById('rx2-ss').textContent,document.querySelectorAll('#rx2-res sl-card').length]"))
    pg.goto('http://127.0.0.1:18091/web/calls.html',wait_until='load');pg.wait_for_timeout(3500)
    pg.evaluate("document.getElementById('nxjNew').click()");pg.wait_for_timeout(8000)
    print('jitsi',pg.evaluate("[document.getElementById('nxjRoom').value,document.getElementById('nxjSt').textContent.slice(0,100),!!document.querySelector('#nxjBox iframe')]"))
    b.close()
P
timeout 150 $N/venv/bin/python /tmp/t1.py 2>&1 | cut -c1-300
