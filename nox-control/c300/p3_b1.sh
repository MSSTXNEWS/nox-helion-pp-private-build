#!/bin/bash
N=/workspace/nox; S=$N/state/p3; T=$(date +%Y%m%d_%H%M%S)
echo "== A) 8104 restart watcher (-t 8 via body_restart.sh when chat silent)"
cat > $S/restart_watch.sh <<'EOW'
#!/bin/bash
N=/workspace/nox; O=$N/state/p3/restart_watch.log
echo "$(date -u +%T) watcher start; cmd -t: $(grep -A1 -x -- '-t' $N/agent/autotrain/donor_hybrid.cmd | tail -1)" >> $O
for i in $(seq 1 240); do
  A=$(( $(date +%s) - $(stat -c %Y $N/state/orch/chat_hold 2>/dev/null || echo 0) ))
  if [ "$A" -gt 150 ]; then
    bash $N/ops/body_restart.sh --reason "P3: -t 8 под cpuset чата" >> $O 2>&1; rc=$?
    echo "$(date -u +%T) body_restart rc=$rc" >> $O
    [ $rc = 0 ] && { sleep 20; python3 /tmp/p3_t.py >> $O 2>&1; python3 /tmp/p3_t.py >> $O 2>&1; echo "after restart: $(ps -o args= -p $(pgrep -f 'port 8104'|head -1) | grep -o -- '-t [0-9]*')" >> $O; exit 0; }
    [ $rc = 2 ] || [ $rc = 4 ] && sleep 120
  fi
  sleep 60
done; echo "$(date -u +%T) watcher gave up (chat never silent 150s for 4h)" >> $O
EOW
chmod +x $S/restart_watch.sh; [ -f /tmp/p3_t.py ] || echo "no /tmp/p3_t.py"; pgrep -f restart_watch.sh >/dev/null || { nohup setsid $S/restart_watch.sh >/dev/null 2>&1 & echo started; }
echo "== B) ritual times 08:00 / 22:30 MSK in living_svc"
F=$N/svc/living/living_svc.py; cp -p $F $F.bak_p3_$T
python3 - "$F" <<'PY'
import sys,re
p=sys.argv[1]; s=open(p).read()
a=s.replace('hour=8, minute=30, args=["morning"]','hour=8, minute=0, args=["morning"]').replace('hour=21, minute=0, args=["evening"]','hour=22, minute=30, args=["evening"]')
print("changed" if a!=s else "NO CHANGE"); open(p,"w").write(a)
PY
$N/venv/bin/python -m py_compile $F && echo "syntax ok" || { cp -p $F.bak_p3_$T $F; echo ROLLBACK; }
grep -n 'add_job' $F | cut -c1-150
P=$(pgrep -f "living_svc.py" | head -1); echo "living pid $P cwd=$(readlink /proc/$P/cwd) ppid=$(ps -o ppid= -p $P)"; echo "cmd: $(tr '\0' ' ' </proc/$P/cmdline)"
