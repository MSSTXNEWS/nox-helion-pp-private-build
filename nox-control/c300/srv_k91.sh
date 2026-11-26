echo "C300: srv_k91"
cd /workspace/nox; mkdir -p models/guard
/workspace/nox/venv/bin/python -I - <<'PY' 2>&1 | grep -v "Warn\|pytree" | tail -25
import json,time,os,sys
from huggingface_hub import snapshot_download
for m in ("muse-models/Muse-Prompt-Shield-1-25M","muse-models/Muse-Prompt-Shield-1-100M"):
    try:
        p=snapshot_download(m,local_dir="/workspace/nox/models/guard/"+m.split("/")[1]); 
        sz=sum(os.path.getsize(os.path.join(r,f)) for r,_,fs in os.walk(p) for f in fs)
        cfg=json.load(open(p+"/config.json")); print(m,"%.0f МБ"%(sz/1e6),cfg.get("architectures"),cfg.get("model_type"),cfg.get("auto_map"))
        rd=open(p+"/README.md",encoding="utf8",errors="ignore").read(); print(rd[:900].replace("\n"," | "))
    except Exception as e: print("ERR",m,repr(e)[:150])
PY
