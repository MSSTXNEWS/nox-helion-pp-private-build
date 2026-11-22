import json, shutil, time, subprocess
B=("Тортилла","Тромсё","черепах")
def bad(x): s=json.dumps(x,ensure_ascii=False); return any(b in s for b in B)
f="/root/nox/state/core_conv_default.json"; shutil.copy(f,f+".bak_test"); d=json.load(open(f))
n=len(d["messages"]); d["messages"]=[m for m in d["messages"] if not bad(m)]; d["_rev"]=d.get("_rev",0)+1 if isinstance(d.get("_rev"),int) else d.get("_rev")
json.dump(d,open(f,"w"),ensure_ascii=False); print("conv removed", n-len(d["messages"]))
f="/root/nox/state/predictive_self.json"; shutil.copy(f,f+".bak_test"); d=json.load(open(f)); k=0
for key in ("history","pending"):
    if isinstance(d.get(key),list): n=len(d[key]); d[key]=[x for x in d[key] if not bad(x)]; k+=n-len(d[key])
json.dump(d,open(f,"w"),ensure_ascii=False); print("pred removed", k)
