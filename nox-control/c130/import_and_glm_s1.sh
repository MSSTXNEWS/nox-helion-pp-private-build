#!/bin/bash
# модель проверена (ALL_OK): остановить шлюз и recall (иначе БД занята), доимпортировать память, поднять всё и GLM
R=/root/nox/repo; git -C $R pull -q 2>&1 | tail -1
pkill -f "glm53/gateway.py"; pkill -f "qs6.recall_server"; sleep 2
pkill -f "llama-server -m /root/nox/glm53" ; sleep 1
timeout 170 bash $R/nox-control/c126/memory_boot_s1.sh 2>&1 | tail -8 | cut -c1-220
echo "== boot"; timeout 100 bash $R/nox-control/c122/boot_s1.sh 2>&1 | tail -6 | cut -c1-200
sleep 5; grep -vE "unused tensor" /root/nox/logs/glm_server.log | tail -4 | cut -c1-200
