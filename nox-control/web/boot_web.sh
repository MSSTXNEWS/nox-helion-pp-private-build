#!/bin/bash
# web-исполнитель: берёт имя скрипта из MODE и выполняет nox-control/web/<MODE>.sh
A=https://api.github.com/repos/MSSTXNEWS/nox-helion-pp-private-build/contents/nox-control/web
H="Accept: application/vnd.github.raw"
M="$(curl -fsSL -H "$H" "$A/MODE?ref=main" | tr -d '[:space:]')"
echo "WEBMODE=$M host=$(hostname)"
curl -fsSL -H "$H" "$A/$M.sh?ref=main" -o /tmp/web_$M.sh && bash /tmp/web_$M.sh 2>&1
