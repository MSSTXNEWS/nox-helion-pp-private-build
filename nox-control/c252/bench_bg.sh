#!/bin/bash
# usage: bench_bg.sh PORT TAG  -> запускает в фоне; читать: cat /root/nox/logs/B_bench_TAG.json
curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c252/bench.py -o /root/nox/bench_B.py
