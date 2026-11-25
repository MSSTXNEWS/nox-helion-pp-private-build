N=/workspace/nox
for i in 1 2 3 4 5 6; do echo -n "$([ -e $N/state/orch/chat_hold ] && echo $(( $(date +%s) - $(stat -c %Y $N/state/orch/chat_hold) )) || echo none) "; sleep 10; done; echo
ps -eo pid,stat,args | awk '$2 ~ /^T/' | cut -c1-100; tail -n 3 $N/state/orch/guard.log | cut -c1-150
