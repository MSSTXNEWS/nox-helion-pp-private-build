echo "C300: k2_r8"
N=/workspace/nox; O=$N/agent/out
sed -n 60,90p $N/canon_night/selfheal_supervisor.sh | cut -c1-200
echo "--- core log bind err ctx"; grep -n -B3 "address already in use" $O/core_8090.log | grep -E "20[0-9]{2}-" | head -3 | cut -c1-160; grep -E "^20[0-9]{2}-[0-9-]+T?[ 0-9:]" $O/core_8090.log | tail -2 | cut -c1-160
echo "--- id_slot usage"; grep -rn "id_slot" $N/web/pkg/server/*.py $N/brain/BRAIN/*.py $N/brain/COMMON/*.py $N/integration/*.py $N/agent/nox_agents/*.py $N/stewards/*.py $N/agent/nox_ops/*.py 2>/dev/null | cut -c1-210 | head -20
echo "--- 8104 callers (files)"; grep -lE "8104" $N/web/pkg/server/*.py $N/brain/BRAIN/*.py $N/brain/COMMON/*.py $N/integration/*.py $N/agent/nox_agents/*.py $N/stewards/*.py $N/agent/nox_ops/*.py $N/cascade/*.py $N/canon_night/*.py 2>/dev/null
echo "--- established conns to 8104"; ss -Htnp state established "( dport = :8104 )" 2>/dev/null | grep -oE 'users:\(\("[a-z_.0-9-]+",pid=[0-9]+' | sort | uniq -c
echo "--- slots"; curl -s -m5 localhost:8104/slots | python3 -c "import sys,json;[print(s.get('id'),s.get('is_processing'),s.get('n_ctx'),(s.get('next_token') or [{}])[0].get('n_decoded')) for s in json.load(sys.stdin)]" 2>&1 | head
