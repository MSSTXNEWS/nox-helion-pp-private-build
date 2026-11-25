#!/bin/bash
cat > /tmp/s2_wlw.py <<'P'
import json,time
from websockets.sync.client import connect
t=time.time()
ws=connect('ws://127.0.0.1:18209',max_size=None,open_timeout=30)
ws.send(json.dumps({'uid':'warm','language':'ru','task':'transcribe','model':'small','use_vad':True}))
while True:
    m=ws.recv(timeout=900); print(round(time.time()-t),str(m)[:120],flush=True)
    if 'SERVER_READY' in str(m): break
time.sleep(2); ws.close()
P
(cd /workspace/nox/svc/whisperlive && nohup setsid venv/bin/python /tmp/s2_wlw.py >/tmp/s2_wlw.log 2>&1 </dev/null &) >/dev/null 2>&1
sleep 45; cat /tmp/s2_wlw.log | tail -5; du -sh /workspace/nox/hf_home/hub/models--Systran--faster-whisper-small
