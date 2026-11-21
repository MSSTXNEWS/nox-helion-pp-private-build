#!/bin/bash
# S1: подтянуть репо, импорт памяти (dry-run -> реально), перезапуск шлюза с памятью/душой, проверка
R=/root/nox/repo; git -C $R pull -q 2>&1 | tail -1
apt-get install -y -qq zstd >/dev/null 2>&1
bash $R/nox-control/c126/memory_boot_s1.sh 2>&1 | tail -14
pkill -f "glm53/gateway.py" 2>/dev/null; sleep 1
timeout 110 bash $R/nox-control/c122/boot_s1.sh 2>&1 | tail -10
sleep 3; curl -s -m 5 http://127.0.0.1:8095/health | head -c 200; echo
curl -s -m 60 http://127.0.0.1:8082/v1/chat/completions -H 'content-type: application/json' -d '{"model":"nox","stream":false,"messages":[{"role":"user","content":"Ты кто и где работаешь?"}]}' | head -c 700; echo
