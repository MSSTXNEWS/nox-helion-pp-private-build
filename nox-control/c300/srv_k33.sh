echo "C300: srv_k33"
cd /workspace/nox
grep -n "^LIVE\|LIVE =\|^EST\|EST =" distill_v2/code/distill_v2.py | cut -c1-200
L=$(grep -o 'LIVE *= *[^#]*' distill_v2/code/distill_v2.py | head -1); echo "$L"
grep -Il "chat_live\|LIVE_FLAG" agent/*.py agent/nox_agents/*.py ops/*.py web/*.py 2>/dev/null | head -8
python3 - <<'PY'
import json
d=json.load(open('/workspace/nox/distill_v2/results_v2.json'))
print({k:d.get(k) for k in ('chat_latency_train_med_s','yield_sec','steps_done','train_sec','tokens_per_sec','peak_vram_mib')})
PY
ls -la --time-style=full-iso state/orch 2>/dev/null | head
