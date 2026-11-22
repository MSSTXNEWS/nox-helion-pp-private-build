#!/bin/bash
bash <(curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c252/bench_bg.sh)
rm -f /root/nox/logs/B_bench_base.json
nohup setsid python3 /root/nox/bench_B.py 8081 base 400 > /root/nox/logs/B_bench_base.out 2>&1 &
sleep 100; cat /root/nox/logs/B_bench_base.out; curl -s -m 5 localhost:8081/slots | python3 -c "import sys,json;print([(s['id'],s['is_processing'],s.get('n_ctx')) for s in json.load(sys.stdin)])"; cat /proc/loadavg
