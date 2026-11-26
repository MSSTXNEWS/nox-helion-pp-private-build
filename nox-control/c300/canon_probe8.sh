#!/bin/bash
echo "C300: canon_probe8"
echo "HOME=$HOME whoami=$(whoami)"
ls -la ~/.config/rclone 2>&1 | head -4 | awk '{print $1,$5,$9}'
rclone config file 2>&1 | head -2
timeout 40 rclone lsd gdrive: 2>&1 | sed -E 's/[A-Za-z0-9_-]{24,}/<ID>/g' | cut -c1-200 | head -4
tail -n 4 $(ls /workspace/nox/backup/*.log /workspace/nox/agent/out/*backup*.log 2>/dev/null | head -2) 2>/dev/null | cut -c1-160
which age age-keygen apt-get curl 2>&1 | head -4
echo "== node_exporter"; which node_exporter; pgrep -af node_exporter | head -1 | cut -c1-80; ss -ltn | grep -c ':9100 '
echo "== gitleaks"; which gitleaks
echo "== graphiti deps"; /workspace/nox/venv/bin/python -c "import neo4j" 2>&1|tail -1; which neo4j redis-server falkordb 2>&1 | head -3
