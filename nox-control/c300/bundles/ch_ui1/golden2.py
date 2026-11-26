import json,re,time,urllib.request,concurrent.futures as cf
GW="http://127.0.0.1:8793"
Q=[("Столица Канады? Одним словом.","Оттав"),("Сколько будет 15*15? Только число.","225"),("Кто написал Преступление и наказание? Фамилия.","Достоевск"),("Химический символ серебра?","Ag"),("Столица Германии? Одним словом.","Берлин"),("Сколько секунд в минуте? Только число.","60")]
cjk=re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]")
have=[m["id"] for m in json.load(urllib.request.urlopen(GW+"/v1/models",timeout=5))["data"]]
try:
    d=json.load(urllib.request.urlopen("https://openrouter.ai/api/v1/models",timeout=15))["data"]
except Exception as e: print("OR ERR",e); d=[]
cand=[]
for m in d:
    i=m.get("id","")
    if not i.endswith(":free"): continue
    if re.search(r"coder|code|embed|vision|vl\b|image|guard|1b|0\.5b|3b|thinking|reason|r1|qwq|safeguard",i,re.I): continue
    kid="kilo/"+i
    if kid in have: continue
    cand.append((m.get("context_length") or 0,kid))
cand=[k for _,k in sorted(cand,reverse=True)][:10]
print("new candidates",cand,flush=True)
def ask(mid,q):
    b={"model":mid,"messages":[{"role":"system","content":"Отвечай только по-русски, коротко."},{"role":"user","content":q+" [g%d]"%int(time.time()*1000)}],"max_tokens":60,"temperature":0.2,"prio":9,"no_cache":True}
    t=time.time()
    try:
        r=json.load(urllib.request.urlopen(urllib.request.Request(GW+"/v1/chat/completions",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=25))
        return (r["choices"][0]["message"]["content"] or "").strip(),time.time()-t,str(r.get("model") or "")
    except Exception as e: return "ERR %s"%str(e)[:50],time.time()-t,""
def one(mid):
    a,s,rm=ask(mid,Q[0][0])
    if a.startswith("ERR") or (mid.split("/",1)[1] not in rm and rm): return mid,-1,s,[(a[:40],rm)]
    ok=1 if re.search(Q[0][1],a,re.I) and not cjk.search(a) else 0; lat=[s]; bad=[] if ok else [a[:30]]
    for q,exp in Q[1:]:
        a,s,rm=ask(mid,q); lat.append(s)
        if cjk.search(a) or not re.search(exp,a,re.I): bad.append(a[:30])
        else: ok+=1
    return mid,ok,sorted(lat)[len(lat)//2],bad
cur=json.load(open("/workspace/nox/state/ch_verified.json")) if True else {}
res=dict(cur.get("models",{}))
with cf.ThreadPoolExecutor(2) as ex:
    for mid,ok,med,bad in ex.map(one,cand):
        print(mid,ok,"/",len(Q),round(med,2),bad[:2],flush=True)
        if ok==len(Q): res[mid]=round(med,2)
json.dump({"ts":int(time.time()),"models":res},open("/workspace/nox/state/ch_verified.json","w"),ensure_ascii=False)
print("VERIFIED",sorted(res.items(),key=lambda x:x[1]))
