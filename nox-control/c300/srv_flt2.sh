#!/bin/bash
python3 -I - <<'PY'
import json,collections,re,urllib.request,os
D="/workspace/nox/distill_v2"
C=collections.Counter(); F=collections.Counter()
CL=re.compile(r"(?i)claude|anthropic|opus|sonnet|haiku-?\d|fable")
ex={}
for l in open(D+"/rows_train.jsonl",encoding="utf-8"):
    if not l.strip(): continue
    r=json.loads(l)
    o=r.get("origin") or r.get("source") or ""; t=r.get("teacher") or ""
    ds=re.sub(r"^https://huggingface.co/datasets/","",str(o))
    k=(ds[:60], str(t)[:40] if not str(t).startswith("ready:") else "ready")
    C[k]+=1
    s=" ".join(str(r.get(x,"")) for x in ("origin","source","teacher","key","kind"))
    if CL.search(s): F[k]+=1
print("distinct origins",len(C)); print("claude-ish hits",sum(F.values())); print(F.most_common(20))
orig=sorted({k[0] for k in C if "/" in k[0]})
print("hf datasets",len(orig))
lic={}
for ds in orig:
    try:
        d=json.load(urllib.request.urlopen("https://huggingface.co/api/datasets/"+ds,timeout=8))
        lic[ds]=(d.get("cardData") or {}).get("license") or [t for t in d.get("tags",[]) if t.startswith("license:")]
    except Exception as e: lic[ds]="ERR"
nc={k:v for k,v in lic.items() if re.search(r"(?i)-nc|noncomm|non-comm",json.dumps(v))}
print("NC datasets:",json.dumps(nc)[:900]); print("ERR",sum(1 for v in lic.values() if v=="ERR"),"unknown",sum(1 for v in lic.values() if not v))
json.dump(lic,open("/workspace/nox/state/p3/hf_licenses.json","w"))
print("rows NC:",sum(c for k,c in C.items() if k[0] in nc))
print("origins w/ opus/claude by name:",[k for k in orig if CL.search(k)][:20])
PY
