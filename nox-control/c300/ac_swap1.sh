echo "C300: ac_swap1"
python3 - <<'PY'
import json
d=json.load(open('/workspace/nox/stewards/orch_registry.json'))
print(d.get('note'))
for i,j in enumerate(d['jobs']):
    if '8812' in ' '.join(map(str,j.get('cmd',[]))): print(i,json.dumps(j,ensure_ascii=False)[:700])
print(sorted({k for j in d['jobs'] for k in j}))
PY
pgrep -af llama-swap | cut -c1-200; ls /workspace/nox/*/llama-swap* /workspace/nox/etc/*swap* 2>/dev/null | head; find /workspace/nox -maxdepth 3 -name "*swap*.y*ml" 2>/dev/null | head
grep -n "enabled\|\"on_demand\"\|disabled" /workspace/nox/stewards/nox_orch.py | head -8
uptime
