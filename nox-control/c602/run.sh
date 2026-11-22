#!/bin/bash
# c602: проверка живого чата через шлюз :8082 (путь веба); работа в фоне, результат /root/nox/state/c602_verify.json
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main
curl -fsS "$R/nox-control/c602/vrun.py?cb=$RANDOM" -o /tmp/c602_vrun.py || exit 1
rm -f /root/nox/state/c602_verify.json.done
nohup setsid python3 /tmp/c602_vrun.py > /root/nox/logs/c602.log 2>&1 &
sleep 1; echo started
python3 - <<'PY'
import json,urllib.request,time
def q(extra,label,mt=500):
    b={"model":"glm","messages":[{"role":"user","content":"Объясни, что такое RAID 1, в 3 предложениях."}],"max_tokens":mt,"temperature":0.7}
    b.update(extra);t=time.time()
    try:
        r=json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8081/v1/chat/completions",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=200))
        m=r["choices"][0]["message"];print(label,'content',len(m.get("content") or ""),'reasoning',len(m.get("reasoning_content") or ""),'fin',r["choices"][0].get("finish_reason"),'toks',r.get("usage",{}).get("completion_tokens"),round(time.time()-t,1),'s')
    except Exception as e: print(label,'ERR',e)
q({},"base");q({"chat_template_kwargs":{"enable_thinking":False}},"ctk_enable_thinking_false");q({"thinking":{"type":"disabled"}},"thinking_disabled")
PY
python3 - <<'PY'
import glob,json,os
fs=sorted(glob.glob('/root/nox/state/core_trace/*'),key=os.path.getmtime)[-11:-1]
for f in fs:
    try: t=json.load(open(f))
    except Exception: 
        try: t=json.loads(open(f).read().strip().splitlines()[-1])
        except Exception: continue
    tr=t.get('trace',t); print(tr.get('intent'),tr.get('path_code'),tr.get('model'),tr.get('degraded'),tr.get('reason_attempts'),tr.get('final_chars'),tr.get('max_tokens'))
PY
