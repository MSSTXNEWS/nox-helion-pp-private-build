#!/bin/bash
sed -n 1,104p /workspace/nox/canon_night/embed_server.py | cut -c1-170
P=$(ps -o ppid= -p 560981 | tr -d ' '); echo ppid $P $(tr '\0' ' ' </proc/$P/cmdline | cut -c1-100)
grep -rn "embed_server" /workspace/nox --include=*.sh --include=*.py --include=*.conf --include=*.json -l 2>/dev/null | grep -v -E "bak|venv|tmp" | head -8
