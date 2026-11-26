#!/bin/bash
cat > /tmp/srv_cc_patch.py <<'PYEOF'
import sys,shutil,time,py_compile
F="/workspace/nox/web/pkg/server/chat_core.py"
s=open(F,encoding="utf-8").read()
if "CC_P3" in s: print("already"); sys.exit(0)
shutil.copy(F,F+".bak_cc_p3_%d"%int(time.time()))
helper='''# CC_P3 (26.11): прямой фолбэк на 8104, если советники не ответили (ответ приходит всегда); пост-проверка не держит поток дольше 8 с
def _p3_direct8104(q, h):
    try:
        import urllib.request as _ur
        t0 = time.time()
        msgs = [dict(m) for m in (h or [])][-6:] + [{"role": "user", "content": str(q)}]
        body = {"model": "x", "messages": msgs, "max_tokens": 500, "temperature": 0.7, "chat_template_kwargs": {"enable_thinking": False}}
        rq = _ur.Request("http://127.0.0.1:8104/v1/chat/completions", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        with _ur.urlopen(rq, timeout=45) as r: d = json.loads(r.read())
        tx = (d["choices"][0]["message"].get("content") or "").strip()
        return {"text": tx, "model": "qwen-8104 (прямой)", "ms": int((time.time() - t0) * 1000), "local": True} if tx else None
    except Exception:
        return None
def _pipe_after(text, ans, cid, body, lv, out):
    th = threading.Thread(target=_pipe_after_inner, args=(text, ans, cid, body, lv, out), daemon=True); th.start(); th.join(8.0)
'''
a="def _pipe_after(text, ans, cid, body, lv, out):"
assert s.count(a)==1
s=s.replace(a,helper+"def _pipe_after_inner(text, ans, cid, body, lv, out):",1)
old='''            if not txt:
                out({"t": "stage", "text": "советники сейчас недоступны (лимит/сбой), жду локальную модель…", "code": "advisors_unavailable"}); return
'''
assert s.count(old)==1
new='''            if not txt:
                out({"t": "stage", "text": "советники сейчас недоступны (лимит/сбой), отвечаю напрямую локальной моделью…", "code": "advisors_unavailable"})
                r = _p3_direct8104(text, h); txt = (r or {}).get("text")   # CC_P3
                if not txt: return
'''
s=s.replace(old,new,1)
o2='out({"t": "race", "winner": "советник",'; assert s.count(o2)==1
s=s.replace(o2,'out({"t": "race", "winner": ("локальная" if r.get("local") else "советник"),',1)
o3='_m["sources"] = list(dict.fromkeys(list(_m.get("sources") or []) + ["советник"]))'; assert s.count(o3)==1
s=s.replace(o3,'_m["sources"] = list(dict.fromkeys(list(_m.get("sources") or []) + [("локальная 8104" if race["adv"].get("local") else "советник")]))',1)
open(F,"w",encoding="utf-8").write(s); py_compile.compile(F,doraise=True); print("patched")
PYEOF
python3 -I /tmp/srv_cc_patch.py || exit 1
python3 -I - <<'PY'
import json,time,re
src=open("/workspace/nox/web/pkg/server/chat_core.py",encoding="utf-8").read()
i=src.index("def _p3_direct8104"); j=src.index("def _pipe_after(")
ns={"json":json,"time":time}; exec(src[i:j],ns)
t=time.time(); r=ns["_p3_direct8104"]("Назови столицу Японии одним словом.",[]); print(round(time.time()-t,1),r)
PY
