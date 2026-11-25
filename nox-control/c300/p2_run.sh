#!/bin/bash
# Экономный запуск c300-скрипта (клиентская часть, на машине исполнителя). Замена /home/claude/run.sh: ~8 вызовов GitHub API на прогон вместо до ~500.
# usage: p2_run.sh NAME [файлы из /home/claude/stage_NAME/ уже скопированы в свой клон]   (клон: /home/claude/p2repo; свой, не общий)
# 1) push (git, не REST)  2) dispatch: gh печатает URL с id прогона, перебор логов не нужен  3) опрос статуса раз в 45 с  4) один раз лог.
N=$1; R=MSSTXNEWS/nox-helion-pp-private-build; cd /home/claude/p2repo || exit 1
git add nox-control/c300/$N.sh 2>/dev/null; git commit -qm "c300: $N (P2 run)" 2>/dev/null
for i in 1 2 3 4 5 6; do git pull -q --rebase origin main && git push -q origin HEAD:main && break; sleep 2; done
URL=$(gh workflow run nox-c300.yml --repo $R --ref main -f script=$N.sh 2>&1 | grep -o 'https://[^ ]*runs/[0-9]*' | head -1); ID=${URL##*/}
[ -n "$ID" ] || { echo "dispatch failed"; exit 1; }; echo "run $ID"
for t in $(seq 1 14); do sleep 45; s=$(gh run view $ID --repo $R --json status -q .status 2>/dev/null); [ "$s" = completed ] && break; done
gh run view $ID --repo $R --log 2>/dev/null | sed 's/^[^\t]*\t[^\t]*\t[^ ]* //' > /home/claude/out_$N.txt; wc -c /home/claude/out_$N.txt
