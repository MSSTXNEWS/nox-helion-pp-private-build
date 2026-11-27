echo "K1: l2_final1"
N=/workspace/nox; F=$N/web/pkg/server/chat_core.py
grep -c -E "L1_DEADLINE|S03_RECALL|S03_FAST" $F; grep -o -E "L1_DEADLINE|S03_RECALL|S03_FAST" $F | sort | uniq -c
python3 -m py_compile $F && echo compiled
supervisorctl status nox_mem nox_rerank nox_stt | cut -c1-80
curl -s -m 3 127.0.0.1:18220/health; echo
python3 - <<'PY'
import json,time,http.client
U="qa-final1"
t0=time.time(); c=http.client.HTTPConnection("127.0.0.1",18091,timeout=90)
c.request("POST","/api/turn",body=json.dumps({"conversation_id":"qa-final1","message":"Привет! Как дела?","user_id":U},ensure_ascii=False).encode(),headers={"Content-Type":"application/json"})
r=c.getresponse(); first=None; end=None
while True:
    l=r.readline()
    if not l: break
    try:o=json.loads(l)
    except Exception: continue
    if o.get("t")=="delta" and first is None: first=time.time()-t0
    if o.get("t") in("done","error"): end=o.get("t"); break
print("qa turn first=%.2f end=%s"%(first or -1,end))
PY
tail -n 5 $N/state/s03_recall.log
df -h /workspace | tail -1 | awk '{print $4}'; nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
