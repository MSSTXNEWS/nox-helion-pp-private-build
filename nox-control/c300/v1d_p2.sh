echo "K1: v1d_p2"
B=http://127.0.0.1:18091
for u in /api/nox/memory/health /api/nox/memory /api/nox/memory/list /api/nox/memory/recall /api/nox/memory/remember /api/nox/memory/save /api/nox/memory/add /api/nox/memory/forget /api/nox/memory/facts /api/nox/memory/stats /api/nox/memory/search /memory/recall /memory/health; do echo "GET $u $(curl -s -m 8 -w ' [%{http_code}]' $B$u | head -c 300)"; done
for u in recall remember save add forget search list; do echo "POST $u $(curl -s -m 8 -X POST -H 'Content-Type: application/json' -d '{"query":"тест","limit":1}' -w ' [%{http_code}]' $B/api/nox/memory/$u | head -c 300)"; done
echo "POST /memory/recall $(curl -s -m 8 -X POST -H 'Content-Type: application/json' -d '{"query":"тест","limit":1}' -w ' [%{http_code}]' $B/memory/recall | head -c 300)"
echo "--- turn raw"
curl -sN -m 70 -X POST -H 'Content-Type: application/json' -d '{"conversation_id":"p2probe","message":"Привет, коротко","mode":"auto","length":"normal","source":"full"}' $B/api/turn | python3 -c '
import sys,json,time
t=time.time();n={}
for l in sys.stdin:
    try:f=json.loads(l)
    except: continue
    k=f.get("t");n[k]=n.get(k,0)+1
    if n[k]<=2 or k in("done","error","meta","meta2"): print("%.1fs"%(time.time()-t),k,json.dumps({a:(b if a!="text" else str(b)[:40]) for a,b in f.items()},ensure_ascii=False)[:400])
print(n)'
echo "--- img"
curl -s -m 90 -X POST -H 'Content-Type: application/json' -d '{"prompt":"красный круг на белом фоне","width":512,"height":512}' -w ' [%{http_code} %{time_total}s]' $B/img/generate | head -c 300
