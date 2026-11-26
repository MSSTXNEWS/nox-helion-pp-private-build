echo "C300: w_d2"
N=/workspace/nox; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
ok=0; for k in 1 2 3 4 5 6 7 8; do t=$(date +%s)$k
 curl -fsSL "$R/w_bridge/api_bridge.py?cb=$t" -o /tmp/api_bridge.py; grep -q 'slots_state' /tmp/api_bridge.py && { ok=1; break; }; sleep 15; done
[ $ok = 1 ] || { echo STALE; exit 0; }
cp $N/ops/api_bridge/api_bridge.py $N/ops/api_bridge/api_bridge.py.bak_d2; cp /tmp/api_bridge.py $N/ops/api_bridge/api_bridge.py
supervisorctl restart nox_api_bridge | tail -1; sleep 3
CF=$N/ops/web_chat_auth/Caddyfile
if ! grep -q 'handle /api/nox/training/status' $CF; then
 cp $CF $CF.bak_d2_$(date +%s)
 PORT=$(grep -o 'BRIDGE_PORT="[0-9]*"' /etc/supervisor/conf.d/nox_api_bridge.conf | grep -o '[0-9]*')
 python3 - $CF $PORT <<'P'
import sys
f,port=sys.argv[1],sys.argv[2]
s=open(f).read()
k="\thandle /api/notifications {"
assert k in s
s=s.replace(k,"\thandle /api/nox/training/status {\n\t\treverse_proxy 127.0.0.1:%s\n\t}\n"%port+k,1)
open(f,'w').write(s);print('inserted')
P
 export HOME=$N/ops/web_chat_auth XDG_CONFIG_HOME=$N/ops/web_chat_auth/xdg XDG_DATA_HOME=$N/ops/web_chat_auth/xdg-data
 if /opt/instance-tools/bin/caddy validate --config $CF --adapter caddyfile 2>&1 | tail -2 | grep -qi valid; then supervisorctl restart nox_web_chat_auth | tail -1; sleep 6; ps -eo pid,cmd | grep -c '[w]eb_chat_auth/Caddyfile'
 else echo VALIDATE_FAIL; ls -t $CF.bak_d2_* | head -1 | xargs -I{} cp {} $CF; fi
fi
for u in nox/activity nox/training/status; do echo "== $u"; for i in 1 2 3; do curl -s -m8 http://127.0.0.1:18091/api/$u | python3 -c "import sys,json;d=json.load(sys.stdin);print({k:v for k,v in d.items() if k in('status','active_generations','per_server','generation_source','hold','generation_slots','verdict')})" 2>&1 | cut -c1-400; done; done
