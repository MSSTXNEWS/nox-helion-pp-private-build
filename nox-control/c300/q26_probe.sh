echo "K1: q26_probe"
export RUNNER_TRACKING_ID=""
python3 - <<'PY'
import json,time,urllib.request,urllib.error,re,threading
FL=["повтор приветствия не в первом ходе","дежурный хвост","ассистентский шаблон","самоопровержение","повтор прошлого ответа","я просто модель","выдуманные факты","неполный ответ","сухо без характера"]
SC={"type":"object","properties":{"p_good":{"type":"number","minimum":0,"maximum":1},"confidence":{"type":"number","minimum":0,"maximum":1},"flags":{"type":"array","items":{"type":"string","enum":FL},"maxItems":3}},"required":["p_good","confidence","flags"]}
SYS="Ты строгий судья ответов. Верни ТОЛЬКО JSON {p_good,confidence,flags}."
U="Вопрос:\nСтолица Австралии?\n\nОтвет для оценки:\nСтолица Австралии — Канберра, а не Сидней."
def post(url,b,hd,to):
    t=time.time()
    try:
        r=urllib.request.urlopen(urllib.request.Request(url,json.dumps(b,ensure_ascii=False).encode(),hd),timeout=to); d=json.loads(r.read()); return "ok",time.time()-t,d
    except urllib.error.HTTPError as e:
        body=e.read()[:300].decode("utf-8","replace"); return "http%d"%e.code,time.time()-t,re.sub(r"[^\w ]"," ",body)[:0]+("len%d"%len(body))
    except Exception as e: return type(e).__name__,time.time()-t,None
H={"Content-Type":"application/json"}
for variant in ("schema","nosch"):
  for i in range(4):
    b={"model":"x","messages":[{"role":"system","content":SYS},{"role":"user","content":U}],"temperature":0,"max_tokens":70,"cache_prompt":True,"chat_template_kwargs":{"enable_thinking":False}}
    if variant=="schema": b["response_format"]={"type":"json_schema","json_schema":{"name":"judge","strict":True,"schema":SC}}
    else: b["messages"][0]["content"]+=" Допустимые флаги: "+"; ".join(FL)
    k,dt,d=post("http://127.0.0.1:8104/v1/chat/completions",b,H,8)
    c=None
    if k=="ok":
        m=d["choices"][0]["message"]; c=m.get("content"); 
        try: json.loads(c[c.index("{"):c.rindex("}")+1]); pj="json"
        except Exception: pj="NOJSON len%d"%len(c or "")
        print("local",variant,k,round(dt,2),pj,"toks",d.get("usage",{}).get("completion_tokens"))
    else: print("local",variant,k,round(dt,2),d)
for i in range(4):
    b={"model":"groq/llama-3.3-70b-versatile","messages":[{"role":"system","content":SYS},{"role":"user","content":U}],"temperature":0,"max_tokens":150,"response_format":{"type":"json_object"}}
    k,dt,d=post("http://127.0.0.1:8793/v1/chat/completions",b,{"Content-Type":"application/json","X-NOX-Priority":"chat"},8)
    if k=="ok":
        c=d["choices"][0]["message"].get("content"); 
        try: json.loads(c[c.index("{"):c.rindex("}")+1]); pj="json"
        except Exception: pj="NOJSON len%d"%len(c or "")
        print("groq",k,round(dt,2),pj,"model",str(d.get("model"))[:25])
    else: print("groq",k,round(dt,2),d)
# concurrency: judge while a generation runs
def gen():
    post("http://127.0.0.1:8104/v1/chat/completions",{"model":"x","messages":[{"role":"user","content":"Расскажи подробно про Python, 300 слов"}],"max_tokens":300,"chat_template_kwargs":{"enable_thinking":False}},H,60)
th=threading.Thread(target=gen);th.start();time.sleep(0.3)
b={"model":"x","messages":[{"role":"system","content":SYS},{"role":"user","content":U}],"temperature":0,"max_tokens":70,"cache_prompt":True,"chat_template_kwargs":{"enable_thinking":False},"response_format":{"type":"json_schema","json_schema":{"name":"judge","strict":True,"schema":SC}}}
print("local_during_gen",*post("http://127.0.0.1:8104/v1/chat/completions",b,H,10)[:2])
th.join()
PY
curl -s http://127.0.0.1:8104/slots 2>/dev/null | python3 -c "import sys,json; s=json.load(sys.stdin); print('slots',len(s),'busy',sum(1 for x in s if x.get('is_processing')))" 2>&1 | tail -1
grep -n "_k1_free_slot" /workspace/nox/web/pkg/server/chat_core.py | head -3 | cut -c1-80
echo END
