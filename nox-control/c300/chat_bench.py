import json,time,sys,urllib.request
Q=["qa-1 Объясни разницу между TCP и UDP в двух предложениях.","qa-2 Напиши функцию на Python, которая проверяет, является ли строка палиндромом.","qa-3 Почему небо голубое? Ответь кратко.","qa-4 Перечисли пять столиц европейских стран и по одному факту о каждой.","qa-5 Придумай короткий тост на день рождения коллеги."]
def one(q,port=8104):
    body=json.dumps({"model":"x","messages":[{"role":"user","content":q}],"max_tokens":128,"temperature":0,"stream":True,"chat_template_kwargs":{"enable_thinking":False}}).encode()
    r=urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions",data=body,headers={"Content-Type":"application/json"})
    t0=time.time();ft=None;n=0
    with urllib.request.urlopen(r,timeout=240) as f:
        for l in f:
            if l.startswith(b"data: {"):
                d=json.loads(l[6:]);c=d["choices"][0]["delta"]
                if c.get("content") or c.get("reasoning_content"):
                    n+=1
                    if ft is None: ft=time.time()-t0
    tt=time.time()-t0
    return ft,n,(n-1)/(tt-ft) if ft and n>1 else 0
R=[one(q) for q in Q]
print("TTFT %.2f s | tok/s %.2f | tokens %d"%(sum(r[0] for r in R)/5,sum(r[2] for r in R)/5,sum(r[1] for r in R)), [(round(r[0],1),round(r[2],1)) for r in R])
