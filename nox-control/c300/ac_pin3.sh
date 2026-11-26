echo "C300: ac_pin3"
T=$(pgrep -f "distill_v2.py train" | head -1)
ls -l /proc/$T/fd/1 /proc/$T/fd/2 | cut -c1-200
L=$(readlink /proc/$T/fd/1); echo L=$L; ls -la $L
grep -aE "s/step|sec|step" $L | tail -25 | cut -c1-200
echo ---; cat /workspace/nox/state/speed.json | python3 -c "import json,sys;d=json.load(sys.stdin);print({k:v for k,v in d.items() if not k.startswith('_why') and 'why' not in k})"
grep -rn "taskset\|sched_setaffinity" /workspace/nox/stewards/nox_orch.py /workspace/nox/stewards/run_orch.sh 2>/dev/null | head -5 | cut -c1-200
