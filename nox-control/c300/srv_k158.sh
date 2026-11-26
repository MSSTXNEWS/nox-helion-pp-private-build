echo "C300: srv_k158"
F=/workspace/nox/web/pkg/server/chat_core.py; N=/workspace/nox
python3 - <<'PY'
F="/workspace/nox/web/pkg/server/chat_core.py"; s=open(F).read()
a='        t.backend = "fast"; out({"t": "meta", "turn_id": t.id, "backend": "fast", "fallback": None})\n'
assert s.count(a)==1
s=s.replace(a,a+'        got[0] = True   # снять гонку/советников\n')
open(F,"w").write(s); print("patched")
PY
python3 -m py_compile $F && echo compiled
pid=$(ss -ltnp | grep "127.0.0.1:8091 " | sed 's/.*pid=\([0-9]*\).*/\1/'); python3 /tmp/relaunch.py $pid $N/web/restart_k1.log http://127.0.0.1:8091/health 2>&1 | tail -1
sleep 150; date -u +%T; timeout 60 python3 /tmp/k1p2.py "Привет, NOX! Как дела?"; tail -n 2 $N/state/chat_fast.log
