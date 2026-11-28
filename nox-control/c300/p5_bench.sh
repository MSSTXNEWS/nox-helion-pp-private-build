echo "K1: p5_bench"; N=/workspace/nox; mkdir -p $N/state/p5
export RUNNER_TRACKING_ID=""
curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/p5_bench.py" -o /tmp/p5_bench.py
echo "slots_busy_before=$(curl -s localhost:8104/slots | python3 -c "import json,sys;print(sum(1 for s in json.load(sys.stdin) if s.get('is_processing')))")"
python3 /tmp/p5_bench.py base 2>&1 | tail -5
echo END
