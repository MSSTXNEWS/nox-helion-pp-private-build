echo "C300: srv_k37"
cd /workspace/nox
grep -n "^def \|^    def " ops/liska_gates.py | cut -c1-170 | head -40
awk '/^def round_gates/{p=1} p{print; n++} n>60{exit}' ops/liska_gates.py | cut -c1-220
grep -n "^def load_model\|^def log\|^IM_END\|^def main\|__name__\|^TARGETS\|^W =\|^NOXD\|^OUT =" distill_v2/code/distill_v2.py | cut -c1-160
sed -n '1860,1872p' distill_v2/code/distill_v2.py | cut -c1-200
echo == real path
cat > /tmp/probe37.py <<'PY'
import json,time,urllib.request
for q in ["Привет! Как дела?","Столица Канады?","Сколько будет 15*15?","Кто написал Преступление и наказание?","Сколько часов в сутках?"]:
    body=json.dumps({"model":"x","messages":[{"role":"user","content":q}],"max_tokens":120,"stream":True}).encode()
    t0=time.time(); ft=None; n=0
    try:
        r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8510/v1/chat/completions",data=body,headers={"Content-Type":"application/json"}),timeout=150)
        for l in r:
            if l.startswith(b'data: {'):
                if ft is None: ft=time.time()-t0
                n+=1
    except Exception as e: print('err',repr(e)[:100])
    print(q[:30],"ttft",round(ft or -1,2),"total",round(time.time()-t0,2),"chunks",n)
PY
/workspace/nox/venv/bin/python -I /tmp/probe37.py
