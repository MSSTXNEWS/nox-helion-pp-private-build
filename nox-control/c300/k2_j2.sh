echo "C300: k2_j2"
N=/workspace/nox; ST=$N/state
cat > $ST/k2_job2.sh <<'J'
#!/bin/bash
N=/workspace/nox; ST=$N/state; L=$ST/k2_job2.log
log(){ echo "$(date -u +%T) $*" >> $L; }
age(){ python3 -c "import time;print(int(time.time()-float(open('$N/state/orch/OWNER_ACTIVE').read().split()[0])))"; }
for i in $(seq 60); do grep -q "MEASURE DONE" $ST/k2_restart.log && break; sleep 20; done
log "restart-measure done; owner age $(age)"
for i in $(seq 120); do [ $(age) -gt 300 ] && break; sleep 20; done
log "owner age $(age) -> restart core"
$N/venv/bin/python $ST/liska_restart_core.py 2>&1 | tail -3 | cut -c1-200 >> $L
for i in $(seq 40); do curl -s -m3 localhost:8090/health | grep -q . && break; sleep 3; done
log "core health: $(curl -s -m5 -o /dev/null -w %{http_code} localhost:8090/health)"
sleep 10
for k in 1 2 3; do log "DRAW$k: $(timeout 200 python3 /tmp/k2_draw.py 'нарисуй кота' 2>&1 | grep -E '^[0-9.]+s .*(img/file|Подскажи)|^end' | cut -c1-150 | tr '\n' ' ')"; sleep 20; done
PIDS=$(pgrep -f "distill_v2.py train|train_dpo.py|gates_only.py|ext_eval.py|liska_skill_teacher.py|--port 8105 |tensorboard_data_server/bin/server")
for m in "Как дела? Расскажи коротко." "Сколько будет 17*23?" "Что такое DNS?"; do
  sleep 300; for p in $PIDS; do kill -STOP $p 2>/dev/null; done; sleep 2
  r=$(python3 /tmp/k2_turn.py "$m" p 2>&1 | tail -1)
  for p in $PIDS; do kill -CONT $p 2>/dev/null; done
  log "CHAT(paused bg, как при ходе мессира): $r"
done
log "JOB2 DONE"
J
chmod +x $ST/k2_job2.sh
grep -q "def turn" /tmp/k2_turn.py 2>/dev/null && echo turn_py_ok; ls /tmp/k2_draw.py
env RUNNER_TRACKING_ID=k2j2 setsid -f bash $ST/k2_job2.sh </dev/null >/dev/null 2>&1
sleep 2; tail -3 $ST/k2_restart.log; ls -la $ST/liska_restart_core.py | cut -c20-80
