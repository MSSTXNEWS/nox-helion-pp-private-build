echo "K1: l2_mem_dep8"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; F=$N/web/pkg/server/chat_core.py
python3 - <<'PY'
F="/workspace/nox/web/pkg/server/chat_core.py"; s=open(F).read()
a='''        m = _living_call_t("http://127.0.0.1:18220/recall", {"q": text, "cid": cid, "user": _s03_user(cid, body), "incognito": bool(body.get("nox_incognito") or body.get("incognito"))}, 0.25)
'''
b='''        _t0 = time.time(); m = _living_call_t("http://127.0.0.1:18220/recall", {"q": text, "cid": cid, "user": _s03_user(cid, body), "incognito": bool(body.get("nox_incognito") or body.get("incognito"))}, 0.3)
        try: open("/workspace/nox/state/s03_recall.log", "a").write("%s ms=%d hits=%s user_set=%s\\n" % (time.strftime("%H:%M:%S"), int((time.time() - _t0) * 1000), (m or {}).get("hits"), bool(body.get("user_id") or body.get("nox_user_id"))))
        except Exception: pass
'''
assert s.count(a)==1; open(F,"w").write(s.replace(a,b)); print("patched2")
PY
python3 -m py_compile $F && echo compiled || { echo FAIL; }
pid=$(ss -ltnp | grep "127.0.0.1:8091 " | sed 's/.*pid=\([0-9]*\).*/\1/'); python3 /tmp/relaunch.py $pid $N/web/restart_k1.log http://127.0.0.1:8091/health 2>&1 | tail -1
sleep 20
python3 - <<'PY'
import json,time,http.client,urllib.request as ur
U="qa-e2e2"
def P(u,o):
    rq=ur.Request("http://127.0.0.1:"+u,data=json.dumps(o).encode(),headers={"Content-Type":"application/json"}); return json.loads(ur.urlopen(rq,timeout=20).read())
for f in ["Пользователя зовут Тест","Пользователь живёт в Севастополе","У пользователя есть кошка по имени Мурка"]: P("18220/add_fact",{"fact":f,"user":U})
def turn(cid,q):
    t0=time.time(); c=http.client.HTTPConnection("127.0.0.1",18091,timeout=90)
    c.request("POST","/api/turn",body=json.dumps({"conversation_id":cid,"message":q,"user_id":U},ensure_ascii=False).encode(),headers={"Content-Type":"application/json"})
    r=c.getresponse(); txt="";first=None;meta=None
    while True:
        l=r.readline()
        if not l: break
        try:o=json.loads(l)
        except Exception: continue
        if o.get("t")=="delta":
            if first is None: first=time.time()-t0
            txt+=o.get("text","")
        if o.get("t")=="done": meta=o.get("meta"); break
    return round(first or -1,2),txt[:260].replace("\n"," "),{k:v for k,v in (meta or {}).items() if k.startswith("s03")}
print(turn("qa-e2e2-b","Как зовут мою кошку и где я живу?"))
print(turn("qa-e2e2-c","Расскажи коротко про луну"))
print(P("18220/forget",{"user":U,"all_user":True}))
PY
echo "--- log"; tail -n 6 $N/state/s03_recall.log
