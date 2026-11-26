echo "C300: srv_k61"
cd /workspace/nox
/workspace/nox/venv/bin/python -I - <<'PY'
import json,glob,os
for f in sorted(glob.glob('distill_v2/gates/42a0a20956b7f314-eval-*.json'),key=os.path.getmtime):
    e=json.load(open(f)); print(os.path.basename(f)[-20:], e['t'], e['fid']['score'], 'suite',str(e.get('eval_suite'))[:16], 'bs',e['policy'].get('bs'), 'rt',str(e.get('eval_runtime'))[:120])
PY
F=$(ls ops/fidelity_cases.py brain/*/fidelity_cases.py 2>/dev/null | head -1); echo F=$F
python3 - <<'PY'
import sys,glob,importlib.util
for p in glob.glob('/workspace/nox/ops/fidelity_cases.py')+glob.glob('/workspace/nox/ops/*/fidelity_cases.py'):
    print(p)
PY
find /workspace/nox -maxdepth 3 -name "fidelity_cases.py" -o -maxdepth 3 -name "fidelity_test.py" 2>/dev/null | head
