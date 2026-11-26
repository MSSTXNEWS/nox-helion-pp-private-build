echo "C300: w_u1"
N=/workspace/nox; S=$N/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
ok=0; for k in 1 2 3 4 5 6 7 8; do t=$(date +%s)$k
 for f in w_u1/nox-train-bridge.js w_u1/nox-t44.js ch_dc1/nox-dc-agenda.js w_bridge/api_bridge.py; do curl -fsSL "$R/$f?cb=$t" -o /tmp/u_$(basename $f); done
 grep -q 'nxTB' /tmp/u_nox-train-bridge.js && grep -q 'min-height:44px' /tmp/u_nox-t44.js && grep -q 'nxag' /tmp/u_nox-dc-agenda.js && grep -q 'async def agenda' /tmp/u_api_bridge.py && { ok=1; break; }; sleep 15; done
[ $ok = 1 ] || { echo STALE; exit 0; }
python3 -c "import ast;ast.parse(open('/tmp/u_api_bridge.py').read())" || exit 0
B=$N/ops/api_bridge/api_bridge.py; cp $B $B.bak_u1; cp /tmp/u_api_bridge.py $B; supervisorctl restart nox_api_bridge | tail -1
cp /tmp/u_nox-train-bridge.js $S/nox-train-bridge.js; cp /tmp/u_nox-t44.js $S/nox-t44.js; cp /tmp/u_nox-dc-agenda.js $S/nox-dc-agenda.js
python3 - <<'P'
S='/workspace/nox/web/site/'
def tag(pg,js,after=None):
    try: h=open(S+pg).read()
    except Exception: print('no',pg); return
    if js in h: return
    open(S+pg+'.bak_u1','w').write(h); open(S+pg,'w').write(h.replace('</body>','<script src="./%s?v=u1" defer></script></body>'%js,1)); print('tag',pg,js)
tag('training.html','nox-train-bridge.js'); tag('intents.html','nox-t44.js'); tag('cinema.html','nox-t44.js'); tag('index.html','nox-t44.js'); tag('chat-dc.html','nox-dc-agenda.js')
P
CF=$N/ops/web_chat_auth/Caddyfile
if ! grep -q 'handle /api/nox/agenda' $CF; then
 cp $CF $CF.bak_u1_$(date +%s)
 PORT=$(grep -o 'BRIDGE_PORT="[0-9]*"' /etc/supervisor/conf.d/nox_api_bridge.conf | grep -o '[0-9]*')
 python3 - $CF $PORT <<'P'
import sys
f,port=sys.argv[1],sys.argv[2]
s=open(f).read(); k="\thandle /api/sci/* {"; assert k in s
s=s.replace(k,"\thandle /api/nox/agenda {\n\t\treverse_proxy 127.0.0.1:%s\n\t}\n"%port+k,1); open(f,'w').write(s); print('caddy inserted')
P
 export HOME=$N/ops/web_chat_auth XDG_CONFIG_HOME=$N/ops/web_chat_auth/xdg XDG_DATA_HOME=$N/ops/web_chat_auth/xdg-data
 if /opt/instance-tools/bin/caddy validate --config $CF --adapter caddyfile 2>&1 | tail -2 | grep -qi valid; then supervisorctl restart nox_web_chat_auth | tail -1; sleep 6
 else echo VALIDATE_FAIL; ls -t $CF.bak_u1_* | head -1 | xargs -I{} cp {} $CF; fi
fi
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$(date +%s)") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$(date +%s)") | tail -1
sleep 3; echo -n "agenda: "; curl -s -m10 http://127.0.0.1:18091/api/nox/agenda | python3 -c "import sys,json;d=json.load(sys.stdin);print('ok',d.get('ok'),'hold',d.get('hold'),'ideas',len(d.get('ideas',[])),sorted({i.get('status') for i in d.get('ideas',[])}-{None}))"
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
cat > /tmp/u1.py <<'P'
from playwright.sync_api import sync_playwright
J="""()=>[...document.querySelectorAll('a,button,[role=button],input,summary,select')].filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&getComputedStyle(e).visibility!='hidden'&&(r.width<43||r.height<43)}).slice(0,12).map(e=>e.tagName+'.'+e.className.toString().slice(0,30)+'#'+e.id+' '+Math.round(e.getBoundingClientRect().width)+'x'+Math.round(e.getBoundingClientRect().height))"""
with sync_playwright() as p:
    b=p.chromium.launch(args=['--no-sandbox','--use-gl=swiftshader','--enable-unsafe-swiftshader'])
    for pg_,w in (('training',1440),('intents',390),('cinema',390),('index',1440)):
        try:
            pg=b.new_page(viewport={'width':w,'height':900});errs=[];pg.on('pageerror',lambda e:errs.append(str(e)[:80]))
            pg.goto('http://127.0.0.1:18091/web/%s.html'%pg_,wait_until='load',timeout=60000);pg.wait_for_timeout(6000)
            extra=pg.evaluate("(document.querySelector('#nxTB')||{textContent:'-'}).textContent.slice(0,90)") if pg_=='training' else ''
            r=pg.evaluate(J);print(pg_,w,len(r),r[:8],extra,errs[:2])
        except Exception as e: print(pg_,w,'ERR',str(e)[:80])
    b.close()
P
timeout 170 $N/venv/bin/python /tmp/u1.py 2>&1 | cut -c1-400
