echo "C300: srv_k65"
cd /workspace/nox/ops/dpo
timeout 250 /workspace/nox/venv/bin/python -I build_dpo2.py 4 5 2>&1 | tail -5
cat build2_stats.json 2>&1; head -c 700 dpo2_train.jsonl 2>&1
