#!/bin/bash
grep -o "ms=[0-9]* ok=True" /workspace/nox/state/pipe_err.log | tail -300 | awk '{split($1,a,"=");print a[2]}' | sort -n | awk '{v[NR]=$1} END{print "ok n",NR,"p50",v[int(NR*.5)],"p90",v[int(NR*.9)],"max",v[NR]}'
grep -c "ok=False" /workspace/nox/state/pipe_err.log
curl -s -m5 127.0.0.1:18217/health | head -c 200
