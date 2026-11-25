p="/workspace/nox/svc/pipeline/pipeline_svc.py"; s=open(p,encoding="utf-8").read()
a='_M["l"] = [m["id"] for m in L]'
assert a in s
s=s.replace(a,'_M["l"] = [m["id"] for m in L if not _re.search(r"coder|code", m["id"], _re.I)] or [m["id"] for m in L]',1)
open(p,"w",encoding="utf-8").write(s); print("fast2 patched")
