N=/workspace/nox
grep -c "P3: тест-обвязка" $N/stewards/nox_orch.py; ls $N/stewards/nox_orch.py.bak_p3_* | tail -1
echo "guard pid file $(cat $N/state/orch/guard.pid) alive=$(kill -0 $(cat $N/state/orch/guard.pid) 2>&1 && echo yes)"; pgrep -fa "stewards/chat_guard.py" | cut -c1-120
tail -n 4 $N/state/orch/guard.log | cut -c1-160
echo "hold: $([ -e $N/state/orch/chat_hold ] && echo age $(( $(date +%s) - $(stat -c %Y $N/state/orch/chat_hold) )) || echo none)"
ps -eo pid,stat,args | awk '$2 ~ /^T/' | cut -c1-110
$N/venv/bin/python -c "
import sys; sys.path.insert(0,'$N/stewards'); import nox_orch as O
print([(c,O.is_probe(c)) for c in ['cf691866','cfx123','cship12','nox-draw-accept-1','k3','probe_x']])"
