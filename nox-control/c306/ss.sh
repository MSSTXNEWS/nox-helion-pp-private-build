#!/bin/bash
date -u +%T; cat /root/nox/logs/flash_start.log | cut -c1-220 | tail -20; echo health=$(curl -s -m 3 -o /dev/null -w "%{http_code}" http://127.0.0.1:8081/health)
for f in /root/nox/logs/bench_*.log; do echo "== $f"; tail -n 6 $f | cut -c1-200; done
