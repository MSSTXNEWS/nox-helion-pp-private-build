echo "K1: v8_before"
N=/workspace/nox; U=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
curl -fsSL "$U/v8_bench.py?x=$RANDOM" -o /tmp/v8_bench.py && PORT=18797 $N/voice/venv/bin/python /tmp/v8_bench.py 2>&1 | tail -5
