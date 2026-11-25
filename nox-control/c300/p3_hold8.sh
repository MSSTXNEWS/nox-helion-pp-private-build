N=/workspace/nox; F=$N/stewards/nox_orch.py; T=$(date +%Y%m%d_%H%M%S)
cp -p $F $F.bak_p3b_$T
python3 - "$F" <<'PY'
import sys
p=sys.argv[1]; L=open(p).read().split("\n"); ok=False
for i,l in enumerate(L):
    if l.startswith("PROBE_RX = re.compile(") and "P3: тест-обвязка" not in l:
        print("line:",l[:160]); j=l.rindex('")')
        L[i]=l[:j]+'|^(cf|cfx|cemp|cship|csm)\\d|^nox-draw-accept|^liska-|^qa[-_]'+l[j:]+"  # P3: тест-обвязка pipeline/fix*/run.sh (cf*, cfx*, cemp*, cship*) не ход мессира"; ok=True
    elif "P3: тест-обвязка" in l: ok=True; print("already")
print("patched" if ok else "NOT FOUND"); open(p,"w").write("\n".join(L))
PY
grep -n "^PROBE_RX" $F | cut -c1-260
$N/venv/bin/python -m py_compile $F && echo syntax ok || { cp -p $F.bak_p3b_$T $F; echo ROLLBACK; exit 1; }
$N/venv/bin/python -c "
import sys; sys.path.insert(0,'$N/stewards'); import nox_orch as O
print([(c,O.is_probe(c)) for c in ['cf691866','cfx123','cemp12','cship12','nox-draw-accept-1','k3','probe_x','8123456']])"
G=$(cat $N/state/orch/guard.pid); CMD=$(tr '\0' ' ' </proc/$G/cmdline); CWD=$(readlink /proc/$G/cwd); kill -TERM $G; sleep 4
NG=$(pgrep -f "stewards/chat_guard.py" | head -1); [ -z "$NG" ] && { (cd $CWD && setsid nohup $CMD >> $N/state/orch/guard.stdout 2>&1 9>&- &); sleep 3; NG=$(pgrep -f "stewards/chat_guard.py" | head -1); echo "started manually"; }; echo "guard pid $NG"
for i in 1 2 3 4 5 6 7 8; do echo -n "$([ -e $N/state/orch/chat_hold ] && echo $(( $(date +%s) - $(stat -c %Y $N/state/orch/chat_hold) )) || echo none) "; sleep 8; done; echo
ps -eo pid,stat,args | awk '$2 ~ /^T/' | cut -c1-100
tail -n 3 $N/state/orch/guard.log | cut -c1-140
