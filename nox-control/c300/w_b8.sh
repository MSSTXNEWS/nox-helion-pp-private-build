echo "C300: w_b8"
N=/workspace/nox
kill 3344041; sleep 2; ps -eo pid,cmd | grep -c "[w]eb_chat_auth/Caddyfile"
for u in training/status nox/activity notifications settings nox/status; do echo -n "bridge $u "; curl -s -m5 -w ' [%{http_code}]' http://127.0.0.1:$PORT/api/$u | cut -c1-260; echo; done
CF=$N/ops/web_chat_auth/Caddyfile
if ! grep -q 'nox_api_bridge' $CF; then
 cp $CF $CF.bak_bridge_$(date +%s)
 python3 - $CF $PORT <<'P'
import sys
f,port=sys.argv[1],sys.argv[2]
L=open(f).read().split('\n'); out=[]; done=False
blk="\t# nox_api_bridge: реальные данные для S2-панелей\n"+"".join("\thandle %s {\n\t\treverse_proxy 127.0.0.1:%s\n\t}\n"%(p,port) for p in ('/api/training/status','/api/nox/activity','/api/notifications','/api/settings','/api/nox/status'))
for l in L:
    if not done and l.startswith('\treverse_proxy 127.0.0.1:8091'):
        out+=blk.rstrip('\n').split('\n')+['']; done=True
    out.append(l)
open(f,'w').write('\n'.join(out)); print('inserted',done)
P
 export HOME=$N/ops/web_chat_auth XDG_CONFIG_HOME=$N/ops/web_chat_auth/xdg XDG_DATA_HOME=$N/ops/web_chat_auth/xdg-data
 if /opt/instance-tools/bin/caddy validate --config $CF --adapter caddyfile 2>&1 | tail -2 | grep -qi valid; then supervisorctl restart nox_web_chat_auth | tail -1; sleep 6
 else echo VALIDATE_FAIL; ls -t $CF.bak_bridge_* | head -1 | xargs -I{} cp {} $CF; fi
fi
for u in training/status nox/activity notifications settings nox/status; do echo -n "18091 $u "; curl -s -m6 -w ' [%{http_code}]' http://127.0.0.1:18091/api/$u | cut -c1-200; echo; done
echo -n "18091 index "; curl -s -m5 -L -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18091/web/index.html
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles; mkdir -p /tmp/w18; for f in axe_scan diag_page; do curl -fsSL "$R/w_a11y/$f.py?cb=$(date +%s)" | sed 's/127.0.0.1:8091/127.0.0.1:18091/g' > /tmp/w18/$f.py; done
N=/workspace/nox; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
timeout 100 $N/venv/bin/python /tmp/w18/axe_scan.py index 2>&1 | cut -c1-330
timeout 60 $N/venv/bin/python /tmp/w18/diag_page.py index 2>&1 | sed 's/.*BAD/BAD/' | cut -c1-330
export PATH=$N/tools/node/bin:$PATH
sed 's#127.0.0.1:8091#127.0.0.1:18091#g' $N/tools/uiscore/score.py > $N/tools/uiscore/score18.py
rm -f $N/agent/out/ui_sc/index_*
timeout 120 $N/venv/bin/python $N/tools/uiscore/score18.py own index 2>&1 | tail -2
python3 $N/tools/uiscore/report.py 2>&1 | grep -E '^index ' | cut -c1-170
rm -f $N/tools/uiscore/score18.py
