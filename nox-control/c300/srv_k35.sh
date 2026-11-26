echo "C300: srv_k35"
cd /workspace/nox
timeout 60 grep -l "LIVE_TURN" *.py web/*.py brain/*.py brain/*/*.py router/*.py router/*/*.py integration/*.py 2>/dev/null | head
ls -la --time-style=full-iso agent/LIVE_TURN 2>&1 | head -2
cat > /tmp/probe35.py <<'PY'
import json,time,urllib.request,sys
qs=["Привет! Как дела?","Столица Канады?","Сколько будет 15*15?","Кто написал Преступление и наказание?","Сколько часов в сутках?"]
tot=[]
for q in qs:
    body=json.dumps({"model":"x","messages":[{"role":"user","content":q}],"max_tokens":120,"stream":True,"chat_template_kwargs":{"enable_thinking":False}}).encode()
    t0=time.time(); ft=None; n=0
    try:
        r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8104/v1/chat/completions",data=body,headers={"Content-Type":"application/json"}),timeout=120)
        for l in r:
            if l.startswith(b'data: {'):
                if ft is None: ft=time.time()-t0
                n+=1
    except Exception as e: print('err',repr(e)[:100])
    tt=time.time()-t0; print(q[:30],"ttft",round(ft or -1,2),"total",round(tt,2),"chunks",n,"tps",round(n/max(tt-(ft or 0),0.01),1)); 
PY
echo "== WITH LIVE_TURN"
( while true; do touch agent/LIVE_TURN; sleep 1; done ) & H=$!
sleep 30   # дать тренеру дойти до границы шага
/workspace/nox/venv/bin/python -I /tmp/probe35.py
kill $H; rm -f agent/LIVE_TURN; sleep 1; ls agent/LIVE_TURN 2>&1 | head -1
