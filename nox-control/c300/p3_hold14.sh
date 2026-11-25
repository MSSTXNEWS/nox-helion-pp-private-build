N=/workspace/nox; sleep 100
echo "hold: $([ -e $N/state/orch/chat_hold ] && echo present || echo none)"; ps -eo pid,stat,args | awk '$2 ~ /^T/' | cut -c1-100
tail -n 6 $N/state/orch/orch.log | cut -c1-200
grep -E '"action": "(freeze|thaw|pause|resume|stop|start)' $N/state/orch/decisions.jsonl | tail -4 | cut -c1-230
