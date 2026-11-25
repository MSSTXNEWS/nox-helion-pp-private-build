import re,sys
p="/workspace/nox/web/pkg/server/chat_core.py"; s=open(p,encoding="utf-8").read()
if "_living_pre" in s: print("already patched"); sys.exit(0)
helpers='''# ---- N: движки живого ИИ (память, эмоции, команды) -> сервис 127.0.0.1:18215; флаги persona.json: living_engines; откат: chat_core.py.bak_n_1 ----
def _le(name):
    try:
        with open("/workspace/nox/state/persona.json", encoding="utf-8") as f: d = json.load(f)
        return bool((d.get("living_engines") or {}).get(name))
    except Exception: return False
def _living_call(path, obj, timeout=4.0):
    try:
        import urllib.request as _ur
        rq = _ur.Request("http://127.0.0.1:18215" + path, data=json.dumps(obj).encode(), headers={"Content-Type": "application/json"})
        with _ur.urlopen(rq, timeout=timeout) as r: return json.loads(r.read())
    except Exception: return {}
def _living_pre(text, cid, body):
    if not (_le("mem0") or _le("emotion")): return {}
    inc = bool(body.get("nox_incognito") or body.get("incognito"))
    r = _living_call("/pre", {"text": text, "cid": cid, "incognito": inc, "mem": _le("mem0"), "emo": _le("emotion")})
    return r if isinstance(r, dict) else {}
def _living_ctx(lv):
    c = (lv or {}).get("context")
    return [{"role": "system", "content": c}] if c else []
def _living_post(text, ans, cid, body):
    if _le("mem0") or _le("emotion"):
        __import__("threading").Thread(target=_living_call, args=("/post", {"text": text, "answer": ans[:500], "cid": cid}, 2.0), daemon=True).start()

'''
a="def run_turn(body, emit):"
assert a in s; s=s.replace(a,helpers+a,1)
b='    with LOCK:\n        conv = load_conv(cid)\n        if running_turn(cid):'
assert b in s
sc='''    _lv = _living_pre(text, cid, body)
    if _lv.get("reply") is not None:      # N: /команды памяти и режимов отвечает сервис без модели
        with LOCK:
            conv = load_conv(cid); _now = time.time()
            conv["messages"].append({"id": "m-" + uuid.uuid4().hex[:10], "role": "user", "content": text, "ts": _now, "source": source})
            conv["messages"].append({"id": "m-" + uuid.uuid4().hex[:10], "role": "assistant", "content": str(_lv["reply"]), "ts": _now + 0.01, "source": source, "status": "done", "backend": "living", "meta": _lv.get("meta")})
            save_conv(conv)
        emit({"t": "meta", "conversation_id": cid, "backend": "living"}); emit({"t": "delta", "text": str(_lv["reply"])})
        emit({"t": "done", "status": "done", "backend": "living", "meta": _lv.get("meta"), "n": len(conv["messages"])})
        return
'''
s=s.replace(b,sc+b,1)
c="        history = _persona_prefix() + history"
assert c in s; s=s.replace(c,"        history = _persona_prefix() + _living_ctx(_lv) + history",1)
d='"status": status, "mode": mode, "path": info.get("path")})'
assert d in s; s=s.replace(d,'"status": status, "mode": mode, "path": info.get("path"), "meta": _lv.get("meta")})',1)
e="    t.drop()\n    if err and status == \"error\":"
assert e in s; s=s.replace(e,"    t.drop()\n    _living_post(text, ans, cid, body)\n    if err and status == \"error\":",1)
f='"path": info.get("path"), "mode": mode, "n": len(conv["messages"])})'
assert f in s; s=s.replace(f,'"path": info.get("path"), "mode": mode, "n": len(conv["messages"]), "meta": _lv.get("meta")})',1)
open(p,"w",encoding="utf-8").write(s); print("patched")
