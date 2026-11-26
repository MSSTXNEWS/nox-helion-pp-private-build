p="/workspace/nox/svc/pipeline/pipeline_svc.py"; s=open(p,encoding="utf-8").read()
if "def verified()" in s: print("already"); raise SystemExit
a="import collections\n_REQ = collections.deque()"
assert a in s
s=s.replace(a,'''def verified():
    """CH: модели, прошедшие golden-набор без ошибок/CJK (state/ch_verified.json, свежесть 48 ч), по возрастанию латентности"""
    try:
        d = json.load(open("/workspace/nox/state/ch_verified.json"))
        if time.time() - d.get("ts", 0) > 172800: return []
        have = set(models())
        return [k for k, _v in sorted((d.get("models") or {}).items(), key=lambda x: x[1]) if k in have]
    except Exception: return []
'''+a,1)
a='ids = models()[skip:skip + k] or (["auto"] if not skip else [])'
assert a in s
s=s.replace(a,'ids = (list(only) if only else models()[skip:skip + k]) or (["auto"] if not skip else [])',1)
a="prio=False, skip=0):"
assert a in s
s=s.replace(a,"prio=False, skip=0, only=None):",1)
a="    r = advise(q, None, 700,"
assert a in s
s=s.replace(a,"    r = (advise(q, None, 700, 4.5, 1, 1, msgs, True, 0, verified()) if verified() else []) or advise(q, None, 700,",1)
open(p,"w",encoding="utf-8").write(s); print("ver patched")
