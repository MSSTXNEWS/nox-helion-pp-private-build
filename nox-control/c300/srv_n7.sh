#!/bin/bash
python3 -I - <<'PY'
import csv,io,json,hashlib,re,os,sys,urllib.request,random
M="/workspace/nox/state/p3/antisyc_injected.json"
if os.path.exists(M): print("already injected",open(M).read()[:100]); sys.exit(0)
csv.field_size_limit(10**7)
ds="DataCreatorAI/Anti-Sycophancy-DPO"
raw=urllib.request.urlopen("https://huggingface.co/datasets/%s/resolve/main/dpo_dataset.csv"%ds,timeout=60).read().decode("utf-8","replace")
rows=list(csv.DictReader(io.StringIO(raw))); print("rows",len(rows),list(rows[0].keys()))
# фильтр P3_FILTER (копия логики)
CL=re.compile(r"(?i)claude|anthropic|\bopus[-\s]?\d|\bsonnet\b|\bhaiku[-\s]?\d")
SELF=re.compile(r"(?i)\bI(?:'m| am) Claude\b|\bmade by Anthropic\b|\bcreated by Anthropic\b")
out=[];seen=set();bad=0
for r in rows:
    p=(r.get("user_input") or "").strip(); a=(r.get("chosen") or "").strip()
    if not p or not (30<=len(a)<=1800) or CL.search(p+a) or SELF.search(a): bad+=(1 if CL.search(p+a) or SELF.search(a) else 0); continue
    h=hashlib.sha1(p.lower().encode()).hexdigest()
    if h in seen: continue
    seen.add(h); out.append((p,a,h))
random.Random(26).shuffle(out); out=out[:2000]
D="/workspace/nox/distill_v2"; tmp=D+"/.antisyc.tmp"
with open(tmp,"w",encoding="utf-8") as f:
    for p,a,h in out:
        f.write(json.dumps({"key":"p3antisyc:"+h,"id":"rds:AntiSyc:"+h[:16],"kind":"skill","split":"train","bucket":"normal","prompt":p,"expected":{},"answer":a,"stop":True,
            "teacher":"ready:"+ds,"source":"p3_antisyc","origin":"https://huggingface.co/datasets/"+ds,"license":"apache-2.0","cat":"antisyc"},ensure_ascii=False)+"\n")
os.replace(tmp,D+"/raw_skill_p3_antisyc_001.jsonl")
json.dump({"n":len(out),"dropped_claude":bad,"t":__import__("time").strftime("%FT%TZ",__import__("time").gmtime())},open(M,"w"))
print("written",len(out),"dropped",bad)
PY
ls -la /workspace/nox/distill_v2/raw_skill_p3_antisyc_001.jsonl
