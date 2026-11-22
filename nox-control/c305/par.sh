#!/bin/bash
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c305/flash_bench.py -o /root/nox/flash_bench.py
echo health=$(curl -s -m 5 -o /dev/null -w "%{http_code}" http://127.0.0.1:8081/health)
nohup setsid python3 /root/nox/flash_bench.py par > /root/nox/logs/bench_par.log 2>&1 < /dev/null &
echo started par
