#!/bin/bash
# Бэкап важного (lora, memory, scripts, очередь диспетчера) на ПК владельца через туннель. Временный tar на диске, затем удаляется.
set -e
PC=${PC:-http://127.0.0.1:18765}; TS=$(date +%Y%m%d_%H%M); NAME=nox_backup_$TS.tgz; T=/root/nox/.tmp_backup; mkdir -p $T
curl -fsS -m 8 $PC/backups/ >/dev/null || { echo "BLOCKED: ПК не подключён (запустить PCLINK_START.cmd)"; exit 3; }
need=$(du -sb /root/nox/lora /root/nox/memory /root/nox/scripts 2>/dev/null | awk '{s+=$1} END{print s}'); avail=$(df --output=avail -B1 /root | tail -1)
[ "$avail" -gt "$((need*2))" ] || { echo "BLOCKED: мало места для временного tar"; exit 4; }
tar czf $T/$NAME --warning=no-file-changed /root/nox/lora /root/nox/memory /root/nox/scripts /root/nox/state/dispatcher/state.json /root/nox/state/dispatcher/queue.jsonl 2>/dev/null || [ $? -eq 1 ]
sz=$(stat -c %s $T/$NAME)
code=$(curl -sS -m 3600 -o /tmp/bk.out -w "%{http_code}" -T $T/$NAME $PC/backups/$NAME)
rm -f $T/$NAME
[ "$code" = "201" ] && echo "BACKUP_OK $NAME $sz $(cat /tmp/bk.out)" || { echo "BACKUP_FAIL http=$code $(cat /tmp/bk.out)"; exit 5; }
