#!/bin/bash
python3 -I - <<'PY'
import json,urllib.request,urllib.parse,re
def g(u):
    return json.load(urllib.request.urlopen(u,timeout=15))
seen={}
for q in ("sycophancy","anti-sycophancy","honesty","false premise","hallucination refusal","truthful"):
    try:
        for d in g("https://huggingface.co/api/datasets?search="+urllib.parse.quote(q)+"&limit=40&full=true"):
            seen[d["id"]]=d
    except Exception as e: print("ERR",q,e)
rows=[]
for k,d in seen.items():
    lic=(d.get("cardData") or {}).get("license") or [t for t in d.get("tags",[]) if t.startswith("license:")]
    ls=json.dumps(lic)
    if re.search(r"(?i)-nc|noncomm|unknown|other",ls) or not lic: continue
    rows.append((d.get("downloads",0),k,ls[:40],[t for t in d.get("tags",[]) if t.startswith("size_categories")][:1]))
for r in sorted(rows,reverse=True)[:30]: print(r)
PY
