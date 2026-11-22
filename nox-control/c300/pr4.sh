#!/bin/bash
W=/root/nox/repo/nox-control/wow7; for d in CON PER EMO WORLD CTX PRIME; do echo "$d: $(ls $W/$d 2>/dev/null | grep '\.py$' | tr '\n' ' ' | cut -c1-150)"; done
P=$(pgrep -f 'python3 .*gateway.py'|head -1); echo gw=$P started=$(ps -o lstart= -p $P)
grep -n "\[prime\]" /root/nox/logs/gateway.log | tail -3 | cut -c1-120; wc -l < /root/nox/logs/gateway.log
tr '\0' '\n' < /proc/$P/environ | grep -E "NOX_WOW7|NOX_PRIME|NOX_STATE"
