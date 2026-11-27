echo "K1: v1_02h"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; F=$N/web/pkg/server/chat_core.py
cp -n $F $F.bak_v102b
python3 - <<'PY'
F="/workspace/nox/web/pkg/server/chat_core.py"; s=open(F).read()
a='if str(cid).startswith("qa-"): return True'
assert s.count(a)==1
open(F,"w").write(s.replace(a,'if str(cid).startswith(("qa-", "rv-")): return True   # V1_02: rv- = ревизор'))
PY
python3 -m py_compile $F && echo compiled || { cp $F.bak_v102b $F; echo ROLLED; exit 1; }
curl -sfL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/owner/relaunch.py?cb=$(date +%s)" -o /tmp/relaunch.py
pid=$(ss -ltnp | grep "127.0.0.1:8091 " | sed 's/.*pid=\([0-9]*\).*/\1/'); python3 /tmp/relaunch.py $pid $N/web/restart_k1.log http://127.0.0.1:8091/health 2>&1 | tail -2
sleep 45
bash $N/../tmp/none 2>/dev/null
curl -sfL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/rv_turn.sh?cb=$(date +%s)" -o /tmp/rv_turn_v102.sh && bash /tmp/rv_turn_v102.sh
echo END
