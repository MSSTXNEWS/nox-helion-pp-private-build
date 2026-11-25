N=/workspace/nox
echo "== writers of chat_hold (code)"; grep -rIn --include=*.py --include=*.sh --include=*.js -E "chat_hold" $N/stewards $N/ops $N/agent $N/web/pkg/server $N/svc $N/brain/BRAIN $N/operators $N/*.py 2>/dev/null | grep -v -E "\.bak|/backup/|/venv" | cut -c1-210 | head -30
echo "== age samples"; for i in 1 2 3 4 5 6; do echo -n "$(( $(date +%s) - $(stat -c %Y $N/state/orch/chat_hold) )) "; sleep 5; done; echo; cat $N/state/orch/chat_hold; echo
which inotifywait strace 2>&1 | head -2
