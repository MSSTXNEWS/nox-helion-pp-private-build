p="/workspace/nox/svc/pipeline/pipeline_svc.py"; s=open(p,encoding="utf-8").read()
a='r = advise(q, None, 700, 6.5, 5, 1, msgs, True) or advise(q, None, 700, 5.5, 5, 1, msgs, True, 5)'
if a in s:
    s=s.replace(a,'r = advise(q, None, 700, 12.5, 6, 1, msgs, True)',1); open(p,"w",encoding="utf-8").write(s); print("one-round patched")
else: print("already/anchor missing", "12.5, 6" in s)
