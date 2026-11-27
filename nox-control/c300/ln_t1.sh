echo "K1: ln_t1"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; M=127.0.0.1:18220
J(){ python3 -c "import sys,json
try:
 d=json.load(sys.stdin); print($1)
except Exception as e: print('ERR',type(e).__name__)"; }
echo "== MEM"
f0=$(curl -s -m5 $M/health | J "d['facts']")
S=$(date +%s)
id=$(curl -s -m10 -w '' -X POST $M/add_fact -d '{"user":"launch_t","fact":"Тестовый факт запуска: кодовое слово лунный кактус 7421"}' | J "d['id']"); echo "add_fact id=$id"
curl -s -m10 -X POST $M/list -d '{"user":"launch_t","n":5}' | J "len(d['items'])" | sed 's/^/list items=/'
R=$(curl -s -m15 -X POST $M/recall -d '{"user":"launch_t","q":"какое кодовое слово лунный кактус"}'); echo "$R" | J "('hits',d['hits'],'ms',d['ms'])"
curl -s -m5 -X POST $M/remember -d '{"user":"launch_t","text":"секретная инкогнито запись которая не должна сохраниться ни при каких условиях","incognito":true}' | J "('incognito remember',d)"
curl -s -m5 -X POST $M/recall -d '{"user":"launch_t","q":"инкогнито","incognito":true}' | J "('incognito recall hits',d['hits'])"
sleep 4; f1=$(curl -s -m5 $M/health | J "d['facts']"); echo "facts before=$f0 after_add_incog=$f1 (expect +1)"
curl -s -m10 -X POST $M/forget -d "{\"user\":\"launch_t\",\"id\":$id}" | J "('forgot',d)"
curl -s -m15 -X POST $M/recall -d '{"user":"launch_t","q":"какое кодовое слово лунный кактус"}' | J "('hits after forget',d['hits'])"
curl -s -m10 -X POST $M/forget -d '{"user":"launch_t","all_user":true}' >/dev/null
echo "== LIVING"
L=127.0.0.1:18091/svc/nox-living
curl -s -m8 "$L/emo?text=%D0%BC%D0%BD%D0%B5%20%D0%BE%D1%87%D0%B5%D0%BD%D1%8C%20%D0%B3%D1%80%D1%83%D1%81%D1%82%D0%BD%D0%BE" | J "('emo keys',sorted(d.keys())[:8])"
curl -s -m8 $L/status | J "('status ok',d.get('ok'),'quiet',d.get('quiet'))"
curl -s -m8 "$L/mem/list?n=5" | J "('living mem items',len(d['items']))"
grep -n "incognito" $N/svc/living/living_svc.py | head -6 | cut -c1-150
echo "== SENSORIUM"
find $N -maxdepth 3 -iname '*sensor*' -not -path '*/node_modules/*' -not -path '*/venv*' 2>/dev/null | head -8
curl -s -m8 127.0.0.1:18091/api/nox/self_now | J "('telemetry',sorted(d['data']['telemetry'].keys()),'feelings',len(d['data']['feelings']))"
echo "== INNER LOOP"
ls -t $N/logs/*inner* /root/nox/logs/con_inner.log $N/state/agents/logs/inner* 2>/dev/null | head -3
for f in $(ls -t $N/state/agents/logs/inner-loop.jsonl $N/logs/*inner* /root/nox/logs/con_inner.log 2>/dev/null | head -2); do echo "$f age=$(( $(date +%s)-$(stat -c %Y $f) ))s lines_1h=$(find $f -mmin -60 | wc -l)"; tail -n 400 $f | grep -ciE "fail|error|отказ|traceback|timeout" | sed 's/^/err_in_last400=/'; done
tail -n 3 $N/state/agents/logs/inner-loop.jsonl 2>/dev/null | cut -c1-220
