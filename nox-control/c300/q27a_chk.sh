echo "K1: q27a_chk"
export RUNNER_TRACKING_ID=""
N=/workspace/nox
echo "md5 $(md5sum < $N/web/pkg/server/chat_core.py | cut -c1-32)"
for i in 1 2 3; do python3 - <<'PY'
import json,time,urllib.request,uuid
t0=time.time(); ev={}; n=0
try:
    r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18091/api/turn",json.dumps({"conversation_id":"qa-chk-"+uuid.uuid4().hex[:5],"message":"Который сейчас час по Москве? Ответь цифрами.","mode":"fast","user_id":"owner"}).encode(),{"Content-Type":"application/json"}),timeout=60)
    tx=[]
    for ln in r:
        s=ln.strip()
        if not s: continue
        o=json.loads(s); ev[o.get("t")]=ev.get(o.get("t"),0)+1
        if o.get("t")=="delta": tx.append(o.get("text") or "")
        if o.get("t") in ("done","error"): 
            if o.get("t")=="error": ev["errkeys"]=",".join(sorted(o)); 
            break
    a="".join(tx); print("turn %.1fs len=%d ev=%s"%(time.time()-t0,len(a),json.dumps(ev)))
except Exception as e: print("fail",type(e).__name__,str(e)[:80])
PY
done
echo "fast.log tail:"; tail -6 $N/state/chat_fast.log | cut -c1-80
echo "restarts/health: $(curl -s -m 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:8091/health) 8104=$(curl -s -m 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:8104/health)"
echo "body locks: $(ls /home/claude/brain/BODY_LOCK 2>/dev/null | wc -l)"; ls -la --time-style=+%T $N/state/chat_gate.log | awk '{print $6}'; date +%T
grep -c "Traceback" $N/web/restart_k1.log 2>/dev/null; tail -n 200 $N/web/restart_k1.log 2>/dev/null | grep -oE "[A-Za-z]+Error[^\n]{0,60}" | sort | uniq -c | head -5
echo END
