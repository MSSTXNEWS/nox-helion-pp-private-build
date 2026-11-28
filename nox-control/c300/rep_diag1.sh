echo "K1: rep_diag1"
python3 - <<'PY'
import json,time,urllib.request,uuid,hashlib
T=["Привет! Как ты сегодня?","Кто ты и кто я для тебя?","Сколько будет 17*23+144/12? Покажи шаги.","У меня 3 яблока, я съел одно и купил ещё два раза по столько, сколько осталось. Сколько яблок?","Напиши на Python функцию проверки палиндрома.","Объясни квантовую запутанность в 3 предложениях.","Мне сегодня грустно, всё валится из рук.","Ты просто нейросеть.","Три идеи на вечер, я устал.","Столица Австралии и почему не Сидней?","Стих о Гелионе, 4 строки.","Что ты помнишь о нашем разговоре?"]
for run in range(3):
    cid="qa-rep-"+uuid.uuid4().hex[:5]; seen={}
    for i,q in enumerate(T,1):
        t0=time.time();txt=[];bk=set();nd=0;st=[]
        r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18091/api/turn",json.dumps({"conversation_id":cid,"message":q,"mode":"fast","user_id":"owner"}).encode(),{"Content-Type":"application/json"}),timeout=90)
        for ln in r:
            s=ln.strip()
            if not s: continue
            o=json.loads(s); t=o.get("t")
            if o.get("backend"): bk.add(str(o["backend"]))
            if t=="stage": st.append(str(o.get("code") or "")[:12])
            if t=="delta": txt.append(o.get("text") or ""); nd+=1
            if t in("done","error"): break
        a="".join(txt); h=hashlib.sha1(a.encode()).hexdigest()[:8]
        rep=seen.get(h); seen.setdefault(h,i)
        print("R%d T%02d sha=%s rep_of=%s backend=%s deltas=%d stages=%s sec=%.1f"%(run,i,h,rep,",".join(sorted(bk)),nd,st,time.time()-t0))
PY
echo END
