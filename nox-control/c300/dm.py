import re, shutil, time, subprocess
p="/root/nox/web_server.py"; s=open(p).read(); ts=time.strftime("%H%M%S"); shutil.copy(p,p+".bak_dm_"+ts)
if "_dmem()" in s: print("already"); raise SystemExit
helper='''
_DMEM_OBJ = [None, 0.0]
def _dmem():
    """Память S03 для режима «Глубоко» (тот же MemoryLayer, что у шлюза; душа отдельно, чтобы не ломать кэш префикса)."""
    if _DMEM_OBJ[0] is not None or time.time() - _DMEM_OBJ[1] < 60: return _DMEM_OBJ[0]
    _DMEM_OBJ[1] = time.time()
    try:
        import sys as _s
        if "/root/nox/repo/nox-control" not in _s.path: _s.path.insert(0, "/root/nox/repo/nox-control")
        from qs6.memory_layer import MemoryLayer
        env = dict(os.environ)
        try:
            gp = subprocess.run(["pgrep", "-f", "python3 .*gateway.py"], capture_output=True, text=True).stdout.split()[0]
            for kv in open("/proc/%s/environ" % gp, "rb").read().split(b"\\0"):
                k, _, v = kv.decode("utf-8", "ignore").partition("=")
                if k.startswith("NOX_"): env.setdefault(k, v)
        except Exception: pass
        env.setdefault("NOX_MEMORY_DB", "/root/nox/memory/s03.db"); env["NOX_SOUL"] = "0"
        _DMEM_OBJ[0] = MemoryLayer(env=env)
    except Exception as e:
        print("[deep-mem] init: %s" % e, flush=True)
    return _DMEM_OBJ[0]
'''
# вставить перед первым определением класса
i = s.index("\nclass "); s = s[:i] + "\n" + helper + s[i:]
# 1) память в последнее сообщение пользователя (deep)
anchor = '            _B = 3500; _tot = sum(len(m["content"]) for m in _hist)'
assert s.count(anchor) == 1
mem_in = '''            _drid = "deep-%d" % int(time.time() * 1000)
            try:
                _m = _dmem()
                _prep = _m.prepare(_user_text, _drid) if (_m and _user_text) else None
                _facts = [str(x) for x in ((_prep or {}).get("facts") or []) if str(x).strip()]
                if _facts and _hist and _hist[-1]["role"] == "user":
                    _hist[-1] = {"role": "user", "content": "[Что NOX помнит по теме (используй, если относится к вопросу; новое важнее старого):\\n- " + "\\n- ".join(_facts)[:1800] + "]\\n\\n" + _hist[-1]["content"]}
            except Exception as _e: print("[deep-mem] prepare: %s" % _e, flush=True)
'''
s = s.replace(anchor, mem_in + anchor)
# 2) после ответа — записать в память (только deep: fast пишет шлюз)
a2 = '            _log_turn(_user_text, "".join(_acc))'
assert s.count(a2) == 1
s = s.replace(a2, a2 + '''
            if _deep and ok and _user_text:
                def _dm_after(u=_user_text, a="".join(_acc), h=list(_hist)):
                    try:
                        _m = _dmem()
                        if _m: _m.after_reply(u, a, "deep-%d" % int(time.time() * 1000), h + [{"role": "assistant", "content": a}])
                    except Exception as _e: print("[deep-mem] after: %s" % _e, flush=True)
                threading.Thread(target=_dm_after, daemon=True).start()''')
for need in ("import threading", "import subprocess"):
    pass
open(p, "w").write(s)
hdr = s[:3000]
print("threading" in hdr, "subprocess" in hdr, "time" in hdr)
r = subprocess.run(["python3", "-m", "py_compile", p], capture_output=True, text=True); print("compile", r.returncode, r.stderr[-300:])
if r.returncode: shutil.copy(p+".bak_dm_"+ts, p); print("REVERTED")
