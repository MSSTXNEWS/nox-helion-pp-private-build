echo "C300: w_t3"
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
sleep 3; curl -s http://127.0.0.1:8796/api/nox/self_now | head -c 200; echo; curl -s http://127.0.0.1:8796/api/nox/briefs | head -c 300; echo
