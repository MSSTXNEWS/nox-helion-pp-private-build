echo "C300: ch_st1"
N=/workspace/nox
echo "== chat_core /fast usage"; grep -n "18217\|/fast\|first_delta\|def .*race\|stream" $N/web/pkg/server/chat_core.py 2>/dev/null | cut -c1-220 | head -40
ls $N/web/pkg/server | head -20
echo "== c_test"; sed -n 1,40p $N/svc/pipeline/c_test.py | cut -c1-200
echo "== gw models top"; curl -s -m4 localhost:8793/v1/models | python3 -c "import sys,json;d=json.load(sys.stdin)['data'];L=[m for m in d if m.get('available') and m.get('status')=='ok' and not m.get('needs_key')];print(len(L));print([(m['id'],m.get('latency_ms')) for m in L[:10]])"
echo "== stream probe"; python3 - <<'PY'
import json,time,urllib.request
rq=urllib.request.Request("http://127.0.0.1:8793/v1/chat/completions",json.dumps({"model":"auto","messages":[{"role":"user","content":"Столица Канады? Одним словом."}],"max_tokens":40,"stream":True,"prio":9,"no_cache":True}).encode(),{"Content-Type":"application/json"})
t=time.time()
try:
    r=urllib.request.urlopen(rq,timeout=20); print("hdr",round(time.time()-t,2),r.headers.get("Content-Type"))
    n=0
    for line in r:
        n+=1
        if n<=6: print(round(time.time()-t,2),line[:140])
except Exception as e: print("ERR",e)
PY
