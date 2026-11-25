#!/bin/bash
# c_diag5: read-only — где recall_server.py, его порт, свободные порты, env веб-сервера
N=/workspace/nox
echo "QS6:"; ls -la $N/qs6 2>&1 | head -20
echo "RECALL FILE:"; F=$(find $N -maxdepth 3 -name recall_server.py 2>/dev/null | head -3); echo "$F"
for f in $F; do echo "--- $f"; grep -n 'PORT\|port\|8095\|8096\|argv\|environ' "$f" | cut -c1-200 | head -15; done
echo "ENV FILE:"; grep -n 'MEMORY\|8095' $N/integration/web_core.env 2>&1 | head -5
echo "LISTEN:"; ss -ltn | awk '{print $4}' | grep -E ':809[0-9]' | sort -u
