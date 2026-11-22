#!/bin/bash
# c207: ждёт GLM (:8081, им управляет исполнитель Б) до 200 с, затем S1_00 apply
B=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main
mkdir -p /tmp/v7deploy; curl -fsSL "$B/nox-control/wow7/deploy/S1_00_hotfix.sh?cb=$RANDOM" -o /tmp/v7deploy/S1_00_hotfix.sh
bash /tmp/v7deploy/S1_00_hotfix.sh 2>&1 | tail -c 2400
