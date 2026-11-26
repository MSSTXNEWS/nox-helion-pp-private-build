echo "C300: w_v2"
N=/workspace/nox; S=$N/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
ok=0; for k in 1 2 3 4 5 6; do t=$(date +%s)$k
 for f in w_v1/nox-w2-fix.js w_roles/nox-roles-x2.js w_bridge/api_bridge.py; do curl -fsSL "$R/$f?cb=$t" -o /tmp/v2_$(basename $f); done
 grep -q 'Transition was aborted/' /tmp/v2_nox-w2-fix.js && grep -q 'j.hold_reason' /tmp/v2_nox-roles-x2.js && grep -q '429' /tmp/v2_api_bridge.py && { ok=1; break; }; sleep 15; done
[ $ok = 1 ] || { echo STALE; exit 0; }
python3 -c "import ast;ast.parse(open('/tmp/v2_api_bridge.py').read())" || exit 0
cp /tmp/v2_nox-w2-fix.js $S/nox-w2-fix.js; cp /tmp/v2_nox-roles-x2.js $S/nox-roles-x2.js
B=$N/ops/api_bridge/api_bridge.py; cp $B $B.bak_v2; cp /tmp/v2_api_bridge.py $B; supervisorctl restart nox_api_bridge | tail -1; sleep 3
echo -n "semantic via bridge: "; curl -s -m20 'http://127.0.0.1:18091/api/sci/semantic?q=entropy' | python3 -c "import sys,json;d=json.load(sys.stdin);print('hold',d.get('hold'),(d.get('hold_reason') or '')[:90],'n',len(d.get('data',[])))"
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$(date +%s)") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$(date +%s)") | tail -1
