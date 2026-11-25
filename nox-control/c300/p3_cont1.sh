N=/workspace/nox
echo "chat_hold age $(( $(date +%s) - $(stat -c %Y $N/state/orch/chat_hold) ))s"
echo "== stopped procs (T)"; ps -eo pid,stat,etimes,ni,args | awk '$2 ~ /^T/' | cut -c1-170 | head -20
echo "== who signals: p3 guard signals?"; grep -c -E "kill|STOP" $N/ops/p3_cpuset_guard.sh $N/ops/p3_excl_once.sh
echo "== orch decisions about qa"; grep -i -E "qa_audit|qa" $N/state/orch/decisions.jsonl | tail -4 | cut -c1-250
echo "== orch/arbiter code stopping qa"; grep -n -E "qa_audit|qa_ctl|chromium" $N/stewards/nox_orch.py $N/agent/arbiter.py $N/ops/train_cpu_pause.sh $N/stewards/chat_guard.py $N/stewards/dispatcher_worm.py 2>/dev/null | cut -c1-190 | head -10
echo "== arbiter log tail"; tail -n 6 $N/arbiter.log | cut -c1-200; tail -n 4 $N/state/orch/orch.log | cut -c1-200
A=$(( $(date +%s) - $(stat -c %Y $N/state/orch/chat_hold) ))
if [ "$A" -gt 120 ]; then for p in $(ps -eo pid,stat,args | awk '$2 ~ /^T/ && /qa_audit\.py/ {print $1}'); do kill -CONT $p && echo "CONT $p"; done; else echo "chat active ($A s) - not resuming"; fi
sleep 3; ps -eo pid,stat,args | grep qa_audit | grep -v grep | cut -c1-120
