N=/workspace/nox; F=$N/stewards/nox_orch.py; T=$(date +%Y%m%d_%H%M%S)
cp -p $F $F.bak_p3_$T
python3 - "$F" <<'PY'
import sys
p=sys.argv[1]; s=open(p).read()
old='PROBE_RX = re.compile(r"(?i)^(probe|liska|test|bench)|probe|smoke|_test|-test|bench|alive_p\\d")'
new='PROBE_RX = re.compile(r"(?i)^(probe|liska|test|bench)|probe|smoke|_test|-test|bench|alive_p\\d|^(cf|cfx|cemp|cship|csm)\\d|^nox-draw-accept|^liska-|^qa[-_]")  # P3: тест-обвязка pipeline/fix*/run.sh (cf*, cfx*, cemp*, cship*) не ход мессира')
if "P3: тест-обвязка" in s: print("already")
elif old in s: open(p,"w").write(s.replace(old,new)); print("patched")
else: print("PATTERN NOT FOUND"); sys.exit(1)
PY
$N/venv/bin/python -m py_compile $F && echo syntax ok || { cp -p $F.bak_p3_$T $F; echo ROLLBACK; exit 1; }
$N/venv/bin/python -c "
import sys; sys.path.insert(0,'$N/stewards'); import nox_orch as O
for c in ['cf69186667973584743942','cfx123456','cempl99999','cship12345','nox-draw-accept-1','k3','8123456789012','probe_x','abc-real-user']: print(c, O.is_probe(c))"
echo "== restart chat_guard only (SIGTERM releases everything; cron respawns)"
G=$(cat $N/state/orch/guard.pid 2>/dev/null); echo "guard pid $G: $(tr '\0' ' ' </proc/$G/cmdline 2>/dev/null)"; CMD=$(tr '\0' ' ' </proc/$G/cmdline); CWD=$(readlink /proc/$G/cwd)
kill -TERM $G; sleep 4; kill -0 $G 2>/dev/null && echo "still alive" || echo "guard stopped"
NG=$(pgrep -f "stewards/chat_guard.py" | head -1); if [ -z "$NG" ]; then (cd $CWD && setsid nohup $CMD >> $N/state/orch/guard.stdout 2>&1 9>&- &); sleep 3; NG=$(pgrep -f "stewards/chat_guard.py" | head -1); echo "started manually"; else echo "respawned"; fi; echo "guard pid now $NG"; tail -n 3 $N/state/orch/guard.log | cut -c1-150
echo "== watch hold age 90s"; for i in $(seq 1 9); do echo -n "$([ -e $N/state/orch/chat_hold ] && echo $(( $(date +%s) - $(stat -c %Y $N/state/orch/chat_hold) )) || echo none) "; sleep 10; done; echo
ps -eo pid,stat,args | awk '$2 ~ /^T/' | cut -c1-110
