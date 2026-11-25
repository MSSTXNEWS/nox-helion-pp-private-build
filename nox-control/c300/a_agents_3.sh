cd /workspace/nox
echo "== arbiter.json"; head -c 900 state/arbiter.json; echo; echo "== chat_priority"; head -c 400 state/chat_priority.json; echo
echo "== arbiter.py (activity/tasks refs)"; grep -nE 'task|activity|chat_priority|pause|json' agent/arbiter.py | head -40
echo "== judge routes"; curl -s -m 5 127.0.0.1:8300/openapi.json | python3 -c "import json,sys;d=json.load(sys.stdin);print(list(d['paths']))" 2>&1 | head -3; grep -nE '@app\.(get|post)' judges/judge_service.py | head
echo "== cascade/operators"; ss -ltnp 2>/dev/null | grep -E 'cascade|8400|8130|8793|python' | awk '{print $4,$6}' | head -20; ls router/advisors | head; grep -nE 'port|PORT' router/advisors/advisor_router.py | head -5
echo "== gateway 8793"; curl -s -m 5 127.0.0.1:8793/v1/models | head -c 500; echo
echo "== d_svc_reg usage"; head -30 svc/d_svc_reg.py; ls svc | grep -i regis
echo "== 8104 props"; curl -s -m 5 127.0.0.1:8104/props | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('total_slots'),d.get('default_generation_settings',{}).get('n_ctx'))"
curl -s -m 5 127.0.0.1:8104/slots | python3 -c "import json,sys;print([(s['id'],s['is_processing']) for s in json.load(sys.stdin)])"
echo "== bench 1 stream and 3 streams on 8104 (max_tokens 128)"
cat > /tmp/a_bench.py <<'PY'
import json,time,sys,threading,urllib.request
def one(i,out):
    b=json.dumps({"model":"x","messages":[{"role":"user","content":"Напиши функцию на Python, считающую числа Фибоначчи, и кратко объясни."}],"max_tokens":128,"temperature":0.2,"chat_template_kwargs":{"enable_thinking":False}}).encode()
    t=time.time();r=json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8104/v1/chat/completions",b,{"Content-Type":"application/json"}),timeout=170));dt=time.time()-t
    out[i]=(r["usage"]["completion_tokens"],dt)
for n in (1,3):
    out={};th=[threading.Thread(target=one,args=(i,out)) for i in range(n)];t=time.time();[x.start() for x in th];[x.join() for x in th];T=time.time()-t
    tot=sum(v[0] for v in out.values());print(n,"streams: per-stream tok/s",[round(v[0]/v[1],1) for v in out.values()],"total",round(tot/T,1),"wall",round(T,1))
PY
python3 /tmp/a_bench.py 2>&1 | tail -4
echo "== nproc"; nproc; df -h /workspace | tail -1
echo "== pip dry"; python3 -m venv /tmp/a_v && /tmp/a_v/bin/pip download langgraph huey --no-deps -d /tmp/a_dl -q 2>&1 | tail -2; ls /tmp/a_dl 2>/dev/null
