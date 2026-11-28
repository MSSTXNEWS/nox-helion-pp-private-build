echo "K1: q29_sc_scan"
export RUNNER_TRACKING_ID=""
N=/workspace/nox
python3 - <<'PY'
import json,os
N="/workspace/nox/state/core"
try:
    d=json.load(open(N+"/hunt_requests.json")); r=d.get("requests",[]); print("hunt keys",sorted(d)[:8],"n",len(r),"item keys",sorted(r[0])[:14] if r else None,"statuses",sorted({x.get("status") for x in r}))
except Exception as e: print("hunt err",type(e).__name__)
try:
    L=[json.loads(l) for l in open(N+"/forge_proposals.jsonl") if l.strip()]; print("forge n",len(L),"keys",sorted(L[-1])[:16] if L else None)
except Exception as e: print("forge err",type(e).__name__)
PY
for f in nox_predator.py nox_ledger.py nox_absorb.py autonomy.py; do echo "$f sign=$(grep -ciE 'sign|подпис|FORGE' $N/mods/$f) consent=$(grep -ciE 'consent' $N/mods/$f)"; done
grep -nE "def .*(sign|forge|consent)|--consent|--sign|FORGE" $N/mods/nox_absorb.py $N/mods/nox_predator.py $N/mods/nox_ledger.py | cut -c1-170 | head -16
echo "gate caddyfile: $(ls $N/state/owner_gate/ 2>&1 | tr '\n' ' ')"
G=$N/state/owner_gate/Caddyfile; echo "gate sites: $(grep -cE '^:[0-9]+' $G) reverse_proxy=$(grep -c reverse_proxy $G) request_header=$(grep -c request_header $G)"
M=$N/ops/web_chat_auth/Caddyfile; echo "main sites: $(grep -E '^[:a-zA-Z0-9.*,_ -]+\{' $M | sed -E 's/\{//;s/ +$//' | tr '\n' '|' | sed -E 's/[a-z0-9-]+\.[a-z.]+/DOMAIN/g')  nox_sidecar_block=$(grep -c NOX_SIDECAR $M) matchers=$(grep -c '@nox_sidecar' $M)"
echo "caddy procs: $(pgrep -af 'caddy.*Caddyfile' | sed -E 's#/workspace/nox/##g' | awk '{print $NF}' | sed -E 's#.*/##' | tr '\n' ' ')"
echo END
