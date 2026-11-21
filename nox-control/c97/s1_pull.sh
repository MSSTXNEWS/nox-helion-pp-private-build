#!/bin/bash
# S1: вытянуть бэкап S2 (sftp, докачка reget), проверить sha256
D=/root/nox/backup_s2; mkdir -p $D; cd $D
exec 9>/root/nox/logs/pull.lock; flock -n 9 || { echo running; tail -2 /root/nox/logs/pull.log; exit 0; }
cat > /root/nox/pull_worker.sh <<'W'
cd /root/nox/backup_s2
O="-i /root/.ssh/s2pull -P 11234 -o StrictHostKeyChecking=no -o BatchMode=yes"
cat > /tmp/pull.batch <<'B'
reget /root/nox/backup_final/memory.tar.zstd
reget /root/nox/backup_final/knowledge.tar.zstd
reget /root/nox/backup_final/datasets.tar.zstd
reget /root/nox/backup_final/lora.tar.zstd
reget /root/nox/backup_final/scripts.tar.zstd
reget /root/nox/backup_final/state.tar.zstd
reget /root/nox/backup_final/KNOWLEDGE_TRANSFER.md
reget /root/nox/backup_final/SHA256SUMS
B
for i in 1 2 3 4; do sftp $O -b /tmp/pull.batch root@166.113.48.41 && break; sleep 5; done
sha256sum -c SHA256SUMS
echo PULL_DONE $(date)
W
nohup setsid bash -c 'exec 9>&-; bash /root/nox/pull_worker.sh' > /root/nox/logs/pull.log 2>&1 < /dev/null &
sleep 45; tail -c 600 /root/nox/logs/pull.log | tr '\r' '\n' | tail -5; ls -la $D
