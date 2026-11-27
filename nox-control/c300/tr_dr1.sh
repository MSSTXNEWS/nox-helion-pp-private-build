export RUNNER_TRACKING_ID=""
echo "C300: tr_dr1"
python3 - <<'PY'
import json,time,urllib.request,uuid
def turn(cid,msg,mode="fast",to=100):
    t0=time.time(); ev=[]
    r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18091/api/turn",json.dumps({"conversation_id":cid,"message":msg,"mode":mode}).encode(),{"Content-Type":"application/json"}),timeout=to)
    txt=""
    for ln in r:
        try: o=json.loads(ln)
        except Exception: continue
        k=o.get("t"); 
        if k=="delta": txt+=o.get("text","")
        else: ev.append((round(time.time()-t0,1),k,{kk:str(v)[:80] for kk,v in o.items() if kk not in("t","turn_id","conversation_id")}))
        if k in("done","error"): break
    return ev,txt,round(time.time()-t0,1)
for cid,m in (("qa-dr-"+uuid.uuid4().hex[:5],"Нарисуй кота"),("qa-dr-"+uuid.uuid4().hex[:5],"Привет, как дела?")):
    try:
        ev,txt,s=turn(cid,m); print("TURN",m,s,"s"); print(" TEXT:",txt[:300].replace("\n"," ")); [print(" EV",e) for e in ev[:10]]
    except Exception as e: print("ERR",repr(e)[:150])
PY
echo "== логи ошибок"; tail -5 /workspace/nox/state/pipe_err.log 2>/dev/null | cut -c1-200
for f in /workspace/nox/agent/out/web_server.log /workspace/nox/agent/out/core_8090.log; do echo "-- $f"; grep -a -i -E "error|Traceback|timeout|deadline" $f 2>/dev/null | tail -4 | cut -c1-220; done
curl -s -m4 localhost:8104/slots | python3 -c "import json,sys;d=json.load(sys.stdin);print('slots',[(s.get('id'),s.get('is_processing')) for s in d])" 2>&1 | head -1
echo END
