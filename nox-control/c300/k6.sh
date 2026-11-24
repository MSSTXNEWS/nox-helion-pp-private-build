#!/bin/bash
unzip -l /workspace/nox/agent/stage_0048/NOX_WEB_VENDOR/NOX_WEB_VENDOR.zip 2>/dev/null | grep -i glass | head -3
find /workspace/nox -maxdepth 4 \( -name "tts_server.py" -o -name "stt_server.py" -o -name "recall_server.py" -o -name "recall_api.py" -o -name "*.onnx" -o -name "s03*.db" -o -name "growth*.py" \) 2>/dev/null | grep -v venv | head -15
ls /workspace/nox/memory | head; ls /workspace/nox/models | head -20 | tr '\n' ' '; echo
df -h /workspace | tail -1; free -g | sed -n 2p
grep -n "/drive\|18765\|DRIVE" /workspace/nox/web/pkg/server/web_server.py | head -5 | cut -c1-150
head -40 /workspace/nox/integration/drive_media_20261123/bridge.py | grep -E '"""|serve|route|/api|def ' | head -15 | cut -c1-150
python3 - <<'P'
import json,urllib.request,time
b={"text":"Привет! Кто ты? Одной фразой.","mode":"fast"}
for path,body in (("/api/chat/turn",b),("/api/chat",{"messages":[{"role":"user","content":"Привет! Кто ты?"}],"nox_mode":"fast","stream":False})):
    t=time.time()
    try:
        r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8091"+path,json.dumps(body).encode(),{"Content-Type":"application/json"}),timeout=120); out=r.read().decode()[-300:]
    except Exception as e: out="ERR %s %s"%(e, getattr(e,'read',lambda:b'')()[:150])
    print(path,"%.1fs"%(time.time()-t),out.replace("\n"," ")[:300])
P
