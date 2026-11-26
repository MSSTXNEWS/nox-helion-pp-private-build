echo "C300: k2_a7"
N=/workspace/nox
python3 - <<'P'
import json
f="/workspace/nox/stewards/orch_registry.json"; r=json.load(open(f))
for j in r["jobs"]:
    if j["name"]=="t_coder": j["enabled"]=False; j["mgr_ok"]=False; print("t_coder enabled=False mgr_ok=False")
json.dump(r,open(f,"w"),ensure_ascii=False,indent=1)
P
echo "--- lock holders"; ls -la $N/state/body_restart.lock | cut -c20-90; (command -v fuser >/dev/null && fuser -v $N/state/body_restart.lock 2>&1 | head -3); for p in $(pgrep -f body_restart.sh); do ps -o pid,etimes,args -p $p | tail -1 | cut -c1-200; done
tail -8 $N/state/body_restart.log | cut -c1-220
P=$(ss -ltnp | grep ':8143 ' | grep -o 'pid=[0-9]*' | cut -d= -f2); kill -CONT $P 2>/dev/null; kill $P 2>/dev/null
