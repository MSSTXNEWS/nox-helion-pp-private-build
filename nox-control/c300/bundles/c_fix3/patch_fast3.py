p="/workspace/nox/svc/pipeline/pipeline_svc.py"; s=open(p,encoding="utf-8").read()
a="def advise(prompt, system=None, mt=350, tmo=14, k=2, want=1, msgs=None, prio=False):"
assert a in s
s=s.replace(a,"def advise(prompt, system=None, mt=350, tmo=14, k=2, want=1, msgs=None, prio=False, skip=0):",1)
a="ids = models()[:k] or [\"auto\"]"
assert a in s
s=s.replace(a,"ids = models()[skip:skip + k] or ([\"auto\"] if not skip else [])",1)
a='    r = advise(q, None, 700, min(float(b.get("tmo") or 12), 12), 3, 1, msgs, True)'
assert a in s
s=s.replace(a,'    r = advise(q, None, 700, 6.5, 5, 1, msgs, True) or advise(q, None, 700, 5.5, 5, 1, msgs, True, 5)   # c_fix3: два раунда по 5 моделей, всего <=13 c (чат ждёт /fast 14 c)',1)
open(p,"w",encoding="utf-8").write(s); print("fast3 patched")
