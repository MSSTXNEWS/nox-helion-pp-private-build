p="/workspace/nox/svc/pipeline/pipeline_svc.py"; s=open(p,encoding="utf-8").read()
a='r = advise(q, None, 700, 12.5, 6, 1, msgs, True)'
if a in s: s=s.replace(a,'r = advise(q, None, 700, 12.5, 3, 1, msgs, True)',1); open(p,"w",encoding="utf-8").write(s); print("k3 patched")
else: print("anchor missing / already", "12.5, 3" in s)
