echo "K1: dz_draw_probe"
N=/workspace/nox; W=$N/web/pkg/server
echo "--- draw refs chat_core"; grep -nE "нарисуй|img/generate|рису|image|stage" $W/chat_core.py | cut -c1-220 | head -40
echo "--- web_server img"; grep -nE "img/generate|/img/|stage" $W/web_server.py | cut -c1-220 | head -20
echo "--- live turn: draw"; t0=$(date +%s)
curl -sN -m 60 -X POST http://127.0.0.1:18091/api/turn -H 'Content-Type: application/json' -d '{"conversation_id":"dzprobe","message":"нарисуй простой красный круг на белом фоне","mode":"auto","length":"short","source":"full"}' | python3 -c '
import sys,json,time
t0=time.time()
for ln in sys.stdin:
    ln=ln.strip()
    if not ln: continue
    try: f=json.loads(ln)
    except Exception: print("raw",ln[:100]); continue
    def sh(v):
        if isinstance(v,str): return v[:80]+("..(%d)"%len(v) if len(v)>80 else "")
        if isinstance(v,dict): return {k:sh(x) for k,x in v.items()}
        if isinstance(v,list): return [sh(x) for x in v[:3]]
        return v
    print("%.1fs"%(time.time()-t0),json.dumps(sh(f),ensure_ascii=False)[:400])
' | head -60
echo "elapsed $(( $(date +%s)-t0 ))s"
echo "--- live turn: memory/stages"; curl -sN -m 40 -X POST http://127.0.0.1:18091/api/turn -H 'Content-Type: application/json' -d '{"conversation_id":"dzprobe2","message":"что ты помнишь обо мне?","mode":"auto","length":"short","source":"full"}' | python3 -c '
import sys,json
seen={}
for ln in sys.stdin:
    try: f=json.loads(ln)
    except Exception: continue
    k=f.get("t"); seen[k]=seen.get(k,0)+1
    if k not in("delta",) and seen[k]<=3: print(json.dumps(f,ensure_ascii=False)[:300])
print(seen)' | head -30
