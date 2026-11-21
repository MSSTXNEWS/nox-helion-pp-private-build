#!/bin/bash
# Загрузка блока 1 (D01-01..20) на сервер и запуск по режиму из MODE: dry | check | run | status
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/block1
mkdir -p /root/nox/scripts /root/nox/logs /root/nox/receipts
curl -fsSL "$R/NOX_BLOCK1.tgz" -o /tmp/b1.tgz && tar xzf /tmp/b1.tgz -C /root/nox/ || { echo "download/extract failed"; exit 1; }
MODE="$(curl -fsSL "$R/MODE" | tr -d '[:space:]')"
chmod +x /root/nox/scripts/*.sh /root/nox/scripts/lib/*.sh 2>/dev/null
[ -f /root/nox/nox.env ] || printf 'NOX_SERVER=S1\nNOX_S1_SSH="-p 62281 root@174.88.252.223"\n' > /root/nox/nox.env
SRV=S1; nvidia-smi -L 2>/dev/null | grep -q V100 && SRV=S2
cd /root/nox/scripts
echo "MODE=$MODE SRV=$SRV host=$(hostname)"
case "$MODE" in
  run_dry) NOX_SERVER=$SRV timeout 250 ./run_block1.sh --dry-run 2>&1 | grep -E "===|BLOCKED|FAIL|DRY|ИТОГ" | cut -c1-220 | tail -c 2800;;
  run_check) NOX_SERVER=$SRV timeout 250 ./run_block1.sh --check 2>&1 | grep -E "===|PASS|FAIL|BLOCKED|ИТОГ" | cut -c1-220 | tail -c 2800;;
  run) NOX_SERVER=$SRV nohup setsid ./run_block1.sh > /root/nox/logs/block1_run.log 2>&1 < /dev/null & sleep 100; grep -E "===|PASS|FAIL|BLOCKED|ИТОГ" /root/nox/logs/block1_run.log | cut -c1-220 | tail -c 2600;;
  status) grep -E "===|PASS|FAIL|BLOCKED|ИТОГ" /root/nox/logs/block1_run.log | cut -c1-220 | tail -c 2600; echo ---; for f in /root/nox/receipts/*.json; do python3 -I -c 'import json,sys;d=json.load(open(sys.argv[1]));print(d["id"],d["result"],d.get("reason","")[:90])' "$f" 2>/dev/null; done | tail -40;;
  *) echo "unknown mode $MODE";;
esac
