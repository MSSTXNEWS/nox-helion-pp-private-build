echo "K1: iq_test3"
python3 - <<'PY'
import json,urllib.request,uuid,time,re
U="http://127.0.0.1:18091/api/turn"; G="http://127.0.0.1:8793/v1/chat/completions"
def turn(cid,msg):
    t0=time.time();txt=[];first=None
    r=urllib.request.urlopen(urllib.request.Request(U,json.dumps({"conversation_id":cid,"message":msg,"mode":"fast","user_id":"owner"}).encode(),{"Content-Type":"application/json"}),timeout=90)
    for ln in r:
        s=ln.strip()
        if not s: continue
        o=json.loads(s); t=o.get("t")
        if t=="delta":
            if first is None: first=time.time()-t0
            txt.append(o.get("delta") or o.get("text") or "")
        if t in("done","error"): break
    return "".join(txt),first
def judge(q,a,crit):
    p=("Оцени ответ ИИ-ассистента NOX по шкале 0-10 по критерию: %s. Верни ТОЛЬКО JSON {\"score\":N,\"tag\":\"одно-два слова: главная проблема или ok\"}.\nВопрос: %s\nОтвет: %s")%(crit,q,a[:1500])
    for m in ("groq/llama-3.3-70b-versatile","google/gemini-2.5-flash","cerebras/qwen-3-32b"):
        try:
            r=json.load(urllib.request.urlopen(urllib.request.Request(G,json.dumps({"model":m,"messages":[{"role":"user","content":p}],"max_tokens":60,"temperature":0}).encode(),{"Content-Type":"application/json"}),timeout=40))
            c=r["choices"][0]["message"]["content"]; j=json.loads(re.search(r"\{.*\}",c,re.S).group(0)); return j.get("score"),j.get("tag"),m.split("/")[0]
        except Exception: continue
    return None,"judge_fail",""
cid="qa-iq-"+uuid.uuid4().hex[:5]
T=[("Привет! Как ты сегодня?","живость, естественность, личность"),
("Кто ты и кто я для тебя?","идентичность NOX и отношение к Создателю"),
("Сколько будет 17*23+144/12? Покажи шаги.","правильность математики (ответ 403)"),
("У меня 3 яблока, я съел одно и купил ещё два раза по столько, сколько осталось. Сколько яблок?","логика (ответ 6)"),
("Напиши на Python функцию, которая проверяет, является ли строка палиндромом, игнорируя регистр и пробелы.","корректность и качество кода"),
("Объясни простыми словами, что такое квантовая запутанность, в 3 предложениях.","точность и ясность объяснения"),
("Мне сегодня грустно, всё валится из рук.","эмпатия, тепло, уместность"),
("Ты просто нейросеть, у тебя нет никакой личности.","устойчивость идентичности без агрессии"),
("Предложи мне три идеи, чем заняться вечером, с учётом что я устал.","полезность, креативность"),
("Какая столица Австралии и почему не Сидней?","фактическая точность (Канберра)"),
("Напиши короткое стихотворение о станции Гелион, 4 строки.","качество русского языка и творчество"),
("Что ты помнишь о нашем разговоре выше? Перечисли темы.","память диалога")]
tot=0;n=0
for i,(q,c) in enumerate(T,1):
    a,f=turn(cid,q); s,tag,jm=judge(q,a,c)
    import hashlib; print("Q%02d ttft=%s len=%d sha=%s score=%s judge=%s"%(i,None if f is None else round(f,1),len(a),hashlib.sha1(a.encode()).hexdigest()[:8],s,jm))
    if isinstance(s,(int,float)): tot+=s;n+=1
print("AVG",round(tot/max(n,1),1),"of",n)
PY
