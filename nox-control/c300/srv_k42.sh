echo "C300: srv_k42"
cd /workspace/nox
touch STOP; echo "STOP set $(date -u +%T)"
grep -o '"moe_[a-z_]*": *[^,]*' state/speed.json
grep -h "скорость:" agent/autotrain/rounds/r033/train.log agent/autotrain/rounds/r034/train.log | cut -c1-120
grep -c "" agent/autotrain/rounds/r034/train.log; tail -n 2 agent/autotrain/rounds/r034/train.log | cut -c1-200
python3 - <<'PY'
import json;d=json.load(open('/workspace/nox/state/speed.json'));print({k:v for k,v in d.items() if k.startswith('moe') or k.startswith('_moe')})
PY
