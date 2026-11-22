#!/bin/bash
pkill -f flash_bench.py; pkill -f d3.py; sleep 2
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c305/flash_bench.py -o /root/nox/flash_bench.py
FB_V3=1 nohup setsid python3 /root/nox/flash_bench.py suites > /root/nox/logs/bench_suites3.log 2>&1 < /dev/null &
echo started v3
