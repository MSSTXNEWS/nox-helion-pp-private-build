#!/bin/bash
# c207: ждёт GLM (:8081, им управляет исполнитель Б) до 200 с, затем S1_00 apply
for i in $(seq 1 40); do [ "$(curl -s -m3 -o /dev/null -w %{http_code} http://127.0.0.1:8081/health)" = 200 ] && break; sleep 5; done
echo "glm8081=$(curl -s -m3 -o /dev/null -w %{http_code} http://127.0.0.1:8081/health) gw8082=$(curl -s -m3 -o /dev/null -w %{http_code} http://127.0.0.1:8082/health)"
[ "$(curl -s -m3 -o /dev/null -w %{http_code} http://127.0.0.1:8081/health)" = 200 ] || { echo GLM_DOWN_SKIP; exit 0; }
B=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main
mkdir -p /tmp/v7deploy; curl -fsSL "$B/nox-control/wow7/deploy/S1_00_hotfix.sh?cb=$RANDOM" -o /tmp/v7deploy/S1_00_hotfix.sh
bash /tmp/v7deploy/S1_00_hotfix.sh 2>&1 | tail -c 2400
