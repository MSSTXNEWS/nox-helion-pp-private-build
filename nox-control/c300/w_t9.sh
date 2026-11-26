echo "C300: w_t9"
N=/workspace/nox; S=$N/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
ok=0; for k in 1 2 3 4 5 6 7 8; do t=$(date +%s)$k
 curl -fsSL "$R/ch_dc1/nox-dc-live.js?cb=$t" -o /tmp/live.js; curl -fsSL "$R/ch_dc1/nox-dc-fix.js?cb=$t" -o /tmp/fix.js
 grep -q 'telemetry' /tmp/live.js && grep -q 'nxfix' /tmp/fix.js && { ok=1; break; }; sleep 15; done
[ $ok = 1 ] || { echo STALE; exit 0; }
cp /tmp/live.js $S/nox-dc-live.js; cp /tmp/fix.js $S/nox-dc-fix.js
python3 - <<'P'
S='/workspace/nox/web/site/'
c=open(S+'chat-dc.html').read()
if 'nox-dc-fix.js' not in c:
    open(S+'chat-dc.html.bak_w_t6','w').write(c)
    k='<script src="./nox-dc-live.js?v=l1" defer></script>'
    if k in c: c=c.replace(k,'<script src="./nox-dc-live.js?v=l2" defer></script>\n<script src="./nox-dc-fix.js?v=f1" defer></script>',1)
    else:
        k='<script src="./nox-dc-draw.js'; assert k in c; c=c.replace(k,'<script src="./nox-dc-live.js?v=l2" defer></script>\n<script src="./nox-dc-fix.js?v=f1" defer></script>\n'+k,1)
    open(S+'chat-dc.html','w').write(c); print('chat patched')
P
CF=$N/ops/web_chat_auth/Caddyfile
echo "routes:"; grep -n 'handle /api/\(nox\|sci\|notif\|settings\|training\)' $CF | cut -c1-120
if ! grep -q 'handle /api/nox/self_now' $CF; then
 cp $CF $CF.bak_t6_$(date +%s)
 PORT=$(grep -o 'BRIDGE_PORT="[0-9]*"' /etc/supervisor/conf.d/nox_api_bridge.conf | grep -o '[0-9]*')
 python3 - $CF $PORT <<'P'
import sys
f,port=sys.argv[1],sys.argv[2]
s=open(f).read(); k="\thandle /api/sci/* {"; assert k in s
s=s.replace(k,"\thandle /api/nox/self_now {\n\t\treverse_proxy 127.0.0.1:%s\n\t}\n\thandle /api/nox/briefs {\n\t\treverse_proxy 127.0.0.1:%s\n\t}\n"%(port,port)+k,1); open(f,'w').write(s); print('caddy inserted')
P
 export HOME=$N/ops/web_chat_auth XDG_CONFIG_HOME=$N/ops/web_chat_auth/xdg XDG_DATA_HOME=$N/ops/web_chat_auth/xdg-data
 if /opt/instance-tools/bin/caddy validate --config $CF --adapter caddyfile 2>&1 | tail -2 | grep -qi valid; then supervisorctl restart nox_web_chat_auth | tail -1; sleep 6; ps -eo pid,cmd | grep -c '[w]eb_chat_auth/Caddyfile'
 else echo VALIDATE_FAIL; ls -t $CF.bak_t6_* | head -1 | xargs -I{} cp {} $CF; fi
fi
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$(date +%s)") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$(date +%s)") | tail -1
for u in self_now briefs; do echo -n "$u via 18091: "; curl -s -o /dev/null -w '%{http_code}\n' -m10 http://127.0.0.1:18091/api/nox/$u; done
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
cat > /tmp/t6.py <<'P'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(args=['--no-sandbox','--use-gl=swiftshader','--enable-unsafe-swiftshader'])
    for w in (390,1440):
        pg=b.new_page(viewport={'width':w,'height':800});errs=[];bad=[];pg.on('pageerror',lambda e:errs.append(str(e)[:90]));pg.on('response',lambda r:bad.append(r.url[-40:]+str(r.status)) if r.status>=400 else 0)
        pg.goto('http://127.0.0.1:18091/web/chat-dc.html',wait_until='load');pg.wait_for_timeout(7000)
        print(w,'now',pg.evaluate("(document.querySelector('#dcNow div')||{textContent:'-'}).textContent.slice(0,40)"),'small',pg.evaluate("[...document.querySelector('deep-chat').shadowRoot.querySelectorAll('button')].filter(x=>{const r=x.getBoundingClientRect();return r.width&&(r.width<43||r.height<43)}).length"),errs,bad[:5])
    b.close()
P
timeout 100 $N/venv/bin/python /tmp/t6.py 2>&1 | cut -c1-300
