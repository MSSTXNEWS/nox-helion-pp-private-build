echo "C300: srv_k28"
cb=$(date +%s); curl -s -m 30 "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/dpo/train_dpo.py?cb=$cb" -o /workspace/nox/ops/dpo/train_dpo.py; grep -c loss_weights /workspace/nox/ops/dpo/train_dpo.py
cd /workspace/nox
/workspace/nox/venv/bin/python -I - <<'PY'
import json,glob,time,urllib.request
fs=sorted(glob.glob('state/web/web_conv/qa-a1*.json'))[:6]
d=json.load(open(fs[0])); print(fs[0], type(d).__name__, list(d)[:6] if isinstance(d,dict) else len(d))
def users(d):
    m=d.get('messages') if isinstance(d,dict) else d
    return [x.get('content') or x.get('text') for x in (m or []) if x.get('role')=='user']
qs=[]
for f in fs:
    try: qs+= [u for u in users(json.load(open(f))) if isinstance(u,str) and 5<len(u)<300][:1]
    except Exception as e: print('err',f,e)
print(len(qs),'prompts')
res=[]
for q in qs[:5]:
    body=json.dumps({"model":"x","messages":[{"role":"user","content":q}],"max_tokens":120,"stream":True,"chat_template_kwargs":{"enable_thinking":False}}).encode()
    t0=time.time(); ft=None; n=0
    try:
        r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8104/v1/chat/completions",data=body,headers={"Content-Type":"application/json"}),timeout=120)
        for l in r:
            if l.startswith(b'data: {'):
                if ft is None: ft=time.time()-t0
                n+=1
    except Exception as e: print('err',repr(e)[:100])
    tt=time.time()-t0; res.append((round(ft or -1,2),round(tt,2),n)); print(q[:40].replace('\n',' '),res[-1])
PY
