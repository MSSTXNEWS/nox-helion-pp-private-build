#!/bin/bash
python3 - <<'PY'
import glob,json,os
fs=sorted(glob.glob('/root/nox/state/core_trace/*.json*'),key=os.path.getmtime)[-12:]
print(len(fs),'traces; ',os.path.basename(fs[-1]) if fs else '')
for f in fs:
    try:
        t=json.load(open(f))
    except Exception:
        try: t=json.loads(open(f).read().strip().splitlines()[-1])
        except Exception as e: print('bad',f,e); continue
    tr=t.get('trace',t)
    print(os.path.getmtime(f)//1, tr.get('intent'),tr.get('path_code'),tr.get('model'),'deg=',tr.get('degraded'),'att=',tr.get('reason_attempts'),'ms=',tr.get('total_ms'),'ulen=',len(str(tr.get('user_text',t.get('user_text','')))),'alen=',len(str(t.get('answer',tr.get('answer','')))))
PY
ls /root/nox/repo/nox-control/wow7 | tr '\n' ' '; echo; ls /root/nox/PRIME /root/nox/repo/nox-control/wow7/PRIME 2>&1 | head -3
ss -ltnp 2>/dev/null | grep -E ":(8099|8081|8083|8082|8090)\b" | awk '{print $4,$6}' | cut -c1-90
python3 - <<'PY'
import json,urllib.request,time
def q(url,extra,label,mt=700):
    b={"model":"glm","messages":[{"role":"user","content":"Объясни, что такое RAID 1, в 3 предложениях."}],"max_tokens":mt,"temperature":0.7}
    b.update(extra);t=time.time()
    try:
        r=json.load(urllib.request.urlopen(urllib.request.Request(url,json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=150))
        m=r["choices"][0]["message"];print(label,'content',len(m.get("content") or ""),'reasoning',len(m.get("reasoning_content") or ""),'fin',r["choices"][0].get("finish_reason"),'toks',r.get("usage",{}).get("completion_tokens"),round(time.time()-t,1),'s')
    except Exception as e: print(label,'ERR',e)
u="http://127.0.0.1:8081/v1/chat/completions"
q(u,{},"base")
q(u,{"chat_template_kwargs":{"enable_thinking":False}},"ctk_enable_thinking_false")
PY
