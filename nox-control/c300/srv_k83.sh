echo "C300: srv_k83"
S=/workspace/nox/ops/v5_knowledge_gpu_20261125; P=$S/phase.py
cp $P $P.bak_k1_pause_$(date +%s)
/workspace/nox/venv/bin/python -I - <<'PY'
p='/workspace/nox/ops/v5_knowledge_gpu_20261125/phase.py'; s=open(p,encoding='utf8').read()
a='    if missing:\n        return {"phase": "main", "remaining": missing, "total": len(main["keys"])}\n'
assert s.count(a)==1
b='    if missing and not (stage / "PAUSE_MAIN").is_file():   # K1 26.11: персона-SFT (main) на паузе флагом PAUSE_MAIN -> сразу к раундам знаний. Откат: rm PAUSE_MAIN\n        return {"phase": "main", "remaining": missing, "total": len(main["keys"])}\n'
open(p,'w',encoding='utf8').write(s.replace(a,b))
PY
/workspace/nox/venv/bin/python -I -m py_compile $P && echo COMPILED
touch $S/PAUSE_MAIN; (cd $S && /workspace/nox/venv/bin/python -I phase.py select 2>&1 | tail -1)
echo == hunger
grep -n "^def last_absorb" -A12 /workspace/nox/agents/nox_worms.py | cut -c1-220
grep -rn "hunger.json" /workspace/nox/agents/*.py /workspace/nox/state/core/*.py 2>/dev/null | head -5 | cut -c1-200
ls -la --time-style=+%T /workspace/nox/state/core/hunger.json 2>&1 | cut -c1-120
echo == ttft
cat > /tmp/p95.py <<'PY'
import json,time,urllib.request,statistics
qs=["Привет!","Столица Франции?","2+2?","Назови цвет неба.","Который сейчас год?"]*4
t=[]
for q in qs:
    b=json.dumps({"model":"x","messages":[{"role":"user","content":q}],"max_tokens":24,"stream":True}).encode(); t0=time.time(); ft=None
    try:
        r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8510/v1/chat/completions",data=b,headers={"Content-Type":"application/json"}),timeout=60)
        for l in r:
            if l.startswith(b'data: {') and ft is None: ft=time.time()-t0
    except Exception as e: ft=None
    t.append(ft if ft is not None else 99)
t.sort(); print("n",len(t),"p50",round(t[len(t)//2],2),"p95",round(t[int(len(t)*0.95)-1],2),"min",round(t[0],2),"max",round(t[-1],2))
PY
/workspace/nox/venv/bin/python -I /tmp/p95.py
tail -2 /workspace/nox/agent/out/k1_restart.log; tail -3 /workspace/nox/state/orch/owner_active.log
