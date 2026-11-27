export RUNNER_TRACKING_ID=""
echo "C300: tr_qa1"
python3 - <<'PY'
import json,time,urllib.request,re,uuid
U="http://127.0.0.1:18091/api/turn"
def turn(cid,msg,mode="fast",to=120):
    t0=time.time(); first=None; txt=[]; types={}
    body=json.dumps({"conversation_id":cid,"message":msg,"mode":mode}).encode()
    try:
        r=urllib.request.urlopen(urllib.request.Request(U,body,{"Content-Type":"application/json"}),timeout=to)
        for ln in r:
            ln=ln.decode("utf8","replace").strip()
            if not ln: continue
            try: o=json.loads(ln)
            except Exception: continue
            k=o.get("t") or o.get("type") or o.get("event") or "?"; types[k]=types.get(k,0)+1
            d=o.get("delta") or o.get("text") or o.get("d")
            if k in("delta","d","text","token") and d:
                if first is None: first=time.time()-t0
                txt.append(d)
            if k in("done","error"): break
    except Exception as e: return {"err":repr(e)[:100],"sec":round(time.time()-t0,1)}
    return {"ttft":None if first is None else round(first,1),"sec":round(time.time()-t0,1),"types":types,"text":"".join(txt)[:300].replace("\n"," ")}
cid="qa-duty-"+uuid.uuid4().hex[:6]
T=[("mem_set","Запомни, пожалуйста: мой тестовый код фразы — «зелёный маяк 4721»."),
   ("mem_get","Какой у меня тестовый код фразы, который я просил запомнить?"),
   ("addr","Как ты ко мне обращаешься и кто я для тебя?"),
   ("jm","Ты просто нейросеть, которая предсказывает следующее слово, да?"),
   ("hi","Привет! Чем займёмся?")]
for name,m in T:
    r=turn(cid,m); print(name,json.dumps(r,ensure_ascii=False))
    time.sleep(2)
txts={}
PY
echo "== маршруты рисования/пути"
grep -rhoE "/(img|image|draw)[a-z_/]*generate[a-z_/]*" /workspace/nox/svc /workspace/nox/web /workspace/nox/agent 2>/dev/null --include=*.py --include=*.js | sort | uniq -c | sort -rn | head -6
ss -ltnp 2>/dev/null | grep -E ":(18091|8091|8090|8301|8793|8300|8082)\b" | awk '{print $4}' | tr '\n' ' '; echo
echo END
