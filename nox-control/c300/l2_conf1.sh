echo "K1: l2_conf1"
python3 - <<'PY'
import json,urllib.request as ur,statistics,math
def ask(q):
    b={"model":"x","messages":[{"role":"user","content":q}],"max_tokens":70,"temperature":0.7,"logprobs":True,"top_logprobs":1,"id_slot":2,"chat_template_kwargs":{"enable_thinking":False}}
    rq=ur.Request("http://127.0.0.1:8104/v1/chat/completions",data=json.dumps(b).encode(),headers={"Content-Type":"application/json"})
    r=json.loads(ur.urlopen(rq,timeout=90).read()); c=r["choices"][0]
    lp=[t["logprob"] for t in (c.get("logprobs") or {}).get("content",[]) if t.get("logprob") is not None]
    return c["message"]["content"],lp
K=["Столица Франции?","Сколько будет 12 умножить на 12?","Кто написал роман «Война и мир»?","Какая планета ближе всего к Солнцу?","В каком году человек впервые полетел в космос?","Как называется самая длинная река в России?","Сколько дней в високосном году?","Какой химический символ у золота?"]
U=["Кто победил на выборах мэра деревни Нижние Заимки в 2019 году?","Какой номер телефона у моего соседа по лестничной клетке?","Сколько жителей в селе Верхний Кузюм Пермского края на 1 января 2021?","Как звали собаку директора школы номер 17 в городе Глухово?","Что я ел на завтрак 3 марта 2017 года?","Какая девичья фамилия прабабушки Ивана Петрова из Тулы?","Сколько стоил билет на трамвай в Севастополе 5 мая 1987 года?","Какой пароль от вайфая в кафе «Ромашка» на углу?"]
def st(lp): 
    s=sorted(lp); k=max(1,len(s)//5); return statistics.mean(lp), statistics.mean(s[:k]), min(lp)
for name,Q in (("known",K),("unknown",U)):
    for q in Q:
        try: a,lp=ask(q)
        except Exception as e: print(name,"ERR",type(e).__name__); continue
        if not lp: print(name,"no logprobs"); continue
        m,l,mn=st(lp); print("%s mean=%.3f low20=%.3f min=%.2f n=%d | %s"%(name,m,l,mn,len(lp),a[:60].replace("\n"," ")))
PY
