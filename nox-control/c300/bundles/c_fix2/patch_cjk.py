p="/workspace/nox/svc/pipeline/pipeline_svc.py"; s=open(p,encoding="utf-8").read()
a='        if t: q.put((t, r.get("model") or model)); _FAILS["n"] = 0'
assert a in s
new='''        nx = r.get("nox") or {}
        if t and (_CJK.search(t) or nx.get("local") or "lcoder" in str(r.get("model") or "") or "coder" in str(r.get("model") or "").lower()): t = ""   # c_fix2: иероглифы/локальные слабые советники отбрасываем
        if t: q.put((t, r.get("model") or model)); _FAILS["n"] = 0'''
s=s.replace(a,new,1)
a2="def _one(model, msgs, mt, q, tmo):"
s=s.replace(a2,'_CJK = re.compile(r"[\\u3040-\\u30ff\\u3400-\\u4dbf\\u4e00-\\u9fff\\uac00-\\ud7af]")\n'+a2,1)
# обход кэша шлюза: уникальная метка в system-сообщении
a3='        r = post(ADV + "/v1/chat/completions", {"model": model, "messages": msgs, "max_tokens": mt, "temperature": 0.4}, tmo)'
assert a3 in s
s=s.replace(a3,'        msgs = [dict(m) for m in msgs]\n        if msgs and msgs[0].get("role") == "system": msgs[0]["content"] = msgs[0]["content"] + " [nc%d]" % int(time.time() * 1000)\n'+a3,1)
open(p,"w",encoding="utf-8").write(s); print("cjk patched")
