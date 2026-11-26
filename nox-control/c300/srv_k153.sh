echo "C300: srv_k153"
F=/workspace/nox/web/pkg/server/chat_core.py; N=/workspace/nox
python3 - <<'PY'
F="/workspace/nox/web/pkg/server/chat_core.py"; s=open(F).read()
a='        sysm = [m for m in history if m.get("role") == "system"][:2]\n'
assert s.count(a)==1
s=s.replace(a,'        sysm = [dict(m, content=str(m.get("content") or "")[:700]) for m in history if m.get("role") == "system"][:1]\n')
b='        c = _hc.HTTPConnection("127.0.0.1", 8104, timeout=8); t.conn = c\n'
assert s.count(b)==1
s=s.replace(b, b+'        try: open("/workspace/nox/state/chat_fast.log", "a").write("%s msgs=%d chars=%d\\n" % (time.strftime("%T"), len(msgs), sum(len(str(m.get("content") or "")) for m in msgs)))\n        except Exception: pass\n')
c='                    n += 1; on_delta(v, None)\n'
assert s.count(c)==1
s=s.replace(c,'                    n += 1; on_delta(v, None)\n                    if n == 1:\n                        try: open("/workspace/nox/state/chat_fast.log", "a").write("  первый токен %.2f с\\n" % (time.time() - t0))\n                        except Exception: pass\n')
open(F,"w").write(s); print("patched")
PY
python3 -m py_compile $F && echo compiled
pid=$(ss -ltnp | grep "127.0.0.1:8091 " | sed 's/.*pid=\([0-9]*\).*/\1/'); python3 /tmp/relaunch.py $pid $N/web/restart_k1.log http://127.0.0.1:8091/health 2>&1 | tail -1
sleep 3; timeout 80 python3 /tmp/k1p2.py
cat $N/state/chat_fast.log | tail -5
curl -s -m4 http://127.0.0.1:8104/slots | python3 -c "import sys,json; print([(s['id'],s.get('is_processing')) for s in json.load(sys.stdin)])"
uptime | sed 's/.*load/load/'
