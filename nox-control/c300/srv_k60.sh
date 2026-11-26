echo "C300: srv_k60"
cd /workspace/nox/ops
sed -n '55,100p;197,252p' liska_gates.py | cut -c1-240
ls /workspace/nox/state/p3/eval | head; head -c 1500 /workspace/nox/state/p3/eval/cases.jsonl | tail -c 900
