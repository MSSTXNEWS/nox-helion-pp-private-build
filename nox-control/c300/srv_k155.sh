echo "C300: srv_k155"
F=/workspace/nox/web/pkg/server/chat_core.py; N=/workspace/nox
cp $F $F.bak_k1_fast2_$(date +%H%M)
python3 - <<'PY'
F="/workspace/nox/web/pkg/server/chat_core.py"; s=open(F).read()
a='        sysm = [dict(m, content=str(m.get("content") or "")[:700]) for m in history if m.get("role") == "system"][:1]\n'
assert s.count(a)==1
s=s.replace(a,'        sysm = [{"role": "system", "content": _k1_stable()}]\n')
b='        rest = [m for m in history if m.get("role") != "system"][-6:]\n'
assert s.count(b)==1
s=s.replace(b,'        rest = [dict(m, content=str(m.get("content") or "")[:400]) for m in history if m.get("role") != "system"][-4:]\n')
c='"temperature": 0.7, "chat_template_kwargs": {"enable_thinking": False}}\n        c = _hc.HTTPConnection("127.0.0.1", 8104, timeout=8)'
assert s.count(c)==1
s=s.replace(c,'"temperature": 0.7, "id_slot": 0, "cache_prompt": True, "chat_template_kwargs": {"enable_thinking": False}}\n        c = _hc.HTTPConnection("127.0.0.1", 8104, timeout=8)')
h='''
_K1ST = [None]
def _k1_stable():
    if _K1ST[0] is None:
        try:
            pp = _persona_prefix()
            _K1ST[0] = str((pp[0].get("content") if pp else "") or "")[:600] or "Ты NOX, тёплый ассистент. Отвечай по-русски, по делу."
        except Exception:
            _K1ST[0] = "Ты NOX, тёплый ассистент. Отвечай по-русски, по делу."
    return _K1ST[0]
def _k1_warm_loop():
    import urllib.request as _ur2
    while True:
        try:
            if not os.path.exists("/workspace/nox/state/chat_fast.off"):
                b = {"model": "x", "messages": [{"role": "system", "content": _k1_stable()}, {"role": "user", "content": "Привет"}], "max_tokens": 1, "id_slot": 0, "cache_prompt": True, "chat_template_kwargs": {"enable_thinking": False}}
                _ur2.urlopen(_ur2.Request("http://127.0.0.1:8104/v1/chat/completions", data=json.dumps(b, ensure_ascii=False).encode(), headers={"Content-Type": "application/json"}), timeout=180).read()
        except Exception:
            pass
        time.sleep(240)
threading.Thread(target=_k1_warm_loop, daemon=True).start()
'''
d="def _pipe_after(text, ans, cid, body, lv, out):"
assert s.count(d)==1
s=s.replace(d,h+"\n"+d)
open(F,"w").write(s); print("patched")
PY
python3 -m py_compile $F && echo compiled
pid=$(ss -ltnp | grep "127.0.0.1:8091 " | sed 's/.*pid=\([0-9]*\).*/\1/'); python3 /tmp/relaunch.py $pid $N/web/restart_k1.log http://127.0.0.1:8091/health 2>&1 | tail -1
sleep 100; tail -n 4 $N/state/chat_fast.log; timeout 60 python3 /tmp/k1p2.py
tail -n 3 $N/state/chat_fast.log
