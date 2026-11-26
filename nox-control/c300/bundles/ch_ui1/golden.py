import json,re,time,urllib.request,concurrent.futures as cf
GW="http://127.0.0.1:8793"
Q=[("Столица Канады? Одним словом.","Оттав"),("Сколько будет 15*15? Только число.","225"),("Кто написал Преступление и наказание? Фамилия.","Достоевск"),("Химический символ серебра?","Ag"),("Столица Германии? Одним словом.","Берлин"),("Сколько секунд в минуте? Только число.","60")]
cjk=re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]")
d=json.load(urllib.request.urlopen(GW+"/v1/models",timeout=5))["data"]
C=[m["id"] for m in d if m.get("available") and m.get("status")=="ok" and not m.get("needs_key") and not re.search(r"coder|code|embed|tiny|vision|tts|image|guard|1b|0\.5b|lcoder",m["id"],re.I)]
print("candidates",len(C),flush=True)
def ask(mid,q):
    b={"model":mid,"messages":[{"role":"system","content":"Отвечай только по-русски, коротко."},{"role":"user","content":q+" [g%d]"%int(time.time()*1000)}],"max_tokens":60,"temperature":0.2,"prio":9,"no_cache":True}
    t=time.time()
    try:
        r=json.load(urllib.request.urlopen(urllib.request.Request(GW+"/v1/chat/completions",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=25))
        return (r["choices"][0]["message"]["content"] or "").strip(),time.time()-t,(r.get("nox") or {}).get("local")
    except Exception as e: return "ERR %s"%str(e)[:40],time.time()-t,None
def one(mid):
    ok=0;lat=[];bad=[]
    for q,exp in Q:
        a,s,loc=ask(mid,q); lat.append(s)
        if loc or cjk.search(a) or not re.search(exp,a,re.I): bad.append((q[:18],a[:30]))
        else: ok+=1
    return mid,ok,sorted(lat)[len(lat)//2],bad
res={}
with cf.ThreadPoolExecutor(2) as ex:
    for mid,ok,med,bad in ex.map(one,C):
        print(mid,ok,"/",len(Q),round(med,2),bad[:2],flush=True)
        if ok==len(Q): res[mid]=round(med,2)
json.dump({"ts":int(time.time()),"models":res},open("/workspace/nox/state/ch_verified.json","w"),ensure_ascii=False)
print("VERIFIED",sorted(res.items(),key=lambda x:x[1]))
