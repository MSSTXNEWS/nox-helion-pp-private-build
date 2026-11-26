echo "C300: srv_k159"
F=/workspace/nox/web/pkg/server/chat_core.py; N=/workspace/nox
python3 - <<'PY'
F="/workspace/nox/web/pkg/server/chat_core.py"; s=open(F).read()
a='_hc.HTTPConnection("127.0.0.1", 8104, timeout=8); t.conn = c'
assert s.count(a)==1
s=s.replace(a,'_hc.HTTPConnection("127.0.0.1", 8104, timeout=30); t.conn = c')
open(F,"w").write(s); print("deadline 30s")
PY
python3 -m py_compile $F && echo compiled
pid=$(ss -ltnp | grep "127.0.0.1:8091 " | sed 's/.*pid=\([0-9]*\).*/\1/'); python3 /tmp/relaunch.py $pid $N/web/restart_k1.log http://127.0.0.1:8091/health 2>&1 | tail -1
echo "--- Thinking-2507"; find $N/models -iname "*Thinking-2507*" -size +1G -printf "%s %p\n" 2>/dev/null | head; ls $N/models/subcores 2>/dev/null; ls $N/ops/restart8105.sh $N/serve/restart8105.sh 2>&1 | head -2; df -h /workspace | tail -1
sleep 120; date -u +%T; timeout 60 python3 /tmp/k1p2.py "Привет, NOX! Как дела?"
