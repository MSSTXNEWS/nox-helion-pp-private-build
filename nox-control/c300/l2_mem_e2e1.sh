echo "K1: l2_mem_e2e1"
python3 - <<'PY'
import json,time,http.client,urllib.request as ur
U="qa-e2e1"
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
    return round(first or -1,2),txt[:200].replace("\n"," "),{k:v for k,v in (meta or {}).items() if k.startswith("s03")}
print(turn("qa-e2e1-a","Запомни: меня зовут Тест, я живу в Севастополе, а мою кошку зовут Мурка."))
for i in range(40):
    time.sleep(3); h=json.loads(ur.urlopen("http://127.0.0.1:18220/health").read())
    if h["facts"]>=2 and h["queue"]==0: break
print("health",h)
print(turn("qa-e2e1-b","Как зовут мою кошку и где я живу?"))
print(turn("qa-e2e1-c","Расскажи коротко про луну"))
rq=ur.Request("http://127.0.0.1:18220/forget",data=json.dumps({"user":U,"all_user":True}).encode(),headers={"Content-Type":"application/json"}); print(ur.urlopen(rq).read())
PY
