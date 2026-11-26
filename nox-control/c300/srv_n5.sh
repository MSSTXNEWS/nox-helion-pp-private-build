#!/bin/bash
python3 -I - <<'PY'
import json,urllib.request,re
def raw(u,n=100000):
    return urllib.request.urlopen(u,timeout=20).read(n).decode("utf-8","replace")
for ds in ("DataCreatorAI/Anti-Sycophancy-DPO","schis02/sycophancy-false-premises","Hooshaai/aegis-anti-sycophancy"):
    print("=====",ds)
    try:
        r=raw("https://huggingface.co/datasets/%s/raw/main/README.md"%ds,4000); print(re.sub(r"\n+","\n",r)[:1300])
        info=json.loads(raw("https://huggingface.co/api/datasets/%s/tree/main"%ds)); print([ (x["path"],x.get("size")) for x in info][:8])
        print("CLAUDE mentions:",len(re.findall(r"(?i)claude|anthropic|sonnet|opus",r)),"gpt:",len(re.findall(r"(?i)gpt|openai|gemini",r)))
    except Exception as e: print("ERR",e)
PY
