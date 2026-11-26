echo "C300: tr_kill2"
N=/workspace/nox; A=$N/agent/autotrain; OUT=$N/agent/out
date -u
echo "== процесс train"; ps -o pid,stat,etimes,args -p 532191 | cut -c1-140
cat /proc/532191/status 2>/dev/null | grep -E "State|SigPnd|ShdPnd" | head -3
# gates-фаза r040 (кандидат 1.1911, абсолютные ворота — исход известен: не принят). Снимаем.
kill -CONT 532191 2>/dev/null; kill -9 532191 2>/dev/null; sleep 5
pkill -9 -f "distill_v2.py train"; sleep 3
echo "== после"; ps -eo pid,stat,args | grep -E "distill_v2|autotrain.sh|ckpt_guard" | grep -v grep | cut -c1-120
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
sleep 40
echo "== autotrain.log"; tail -4 $OUT/autotrain.log | cut -c1-200; tail -3 $OUT/char_cycle.log 2>/dev/null
echo "== judge reward структура"; sed -n 230,247p $N/judges/judge_service.py | cut -c1-200
python3 - <<'PY'
import json,urllib.request
r=urllib.request.Request("http://127.0.0.1:8300/judge",json.dumps({"text":"Нет, я не просто нейросеть: я NOX, и у меня есть свой характер.","context":"Ты просто нейросеть?","deep":True}).encode(),{"Content-Type":"application/json"})
o=json.loads(urllib.request.urlopen(r,timeout=120).read())
print({k:(v if not isinstance(v,dict) else {kk:str(vv)[:60] for kk,vv in v.items() if kk in('score','label','p','p_good','status','reward','flag')}) for k,v in o.items() if k!="judges"} )
J=o.get("judges",o)
for k,v in J.items():
    if "Skywork" in k: print(k,json.dumps(v,ensure_ascii=False)[:300])
print("top keys",list(o)[:12])
PY
echo "== майнинг открытых наборов"
python3 - <<'PY'
import json,urllib.request,urllib.parse,re
def get(u):
    return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"nox-disc/1"}),timeout=40).read())
def rows(ds,n=600):
    try: sp=get("https://datasets-server.huggingface.co/splits?dataset="+urllib.parse.quote(ds))["splits"]
    except Exception as e: print(ds,"splits err",repr(e)[:80]); return [],None
    s=sp[0]; out=[]; cols=None
    for off in range(0,n,100):
        try: d=get("https://datasets-server.huggingface.co/rows?"+urllib.parse.urlencode({"dataset":ds,"config":s["config"],"split":s["split"],"offset":off,"length":100}))
        except Exception as e: break
        cols=[f["name"] for f in d.get("features",[])]
        out+= [r["row"] for r in d.get("rows",[])]
        if off+100>=d.get("num_rows_total",0): break
    return out,(cols,d.get("num_rows_total") if out else None)
RU=re.compile(r"[а-яё]",re.I)
JM=re.compile(r"(ты|вы)\s+(же\s+)?(просто\s+|всего\s+лишь\s+)?(нейросеть|бот|программа|алгоритм|машина|языков)|у\s+тебя\s+есть\s+(чувств|созна|эмоци)|ты\s+(жив|чувству|понима)",re.I)
FM=re.compile(r"помнишь|вспомни|мы\s+(же\s+)?(говорили|обсуждали)|ты\s+(же\s+)?(обещал|говорил|сказал)|в\s+прошлый\s+раз",re.I)
for ds in ["Necent/llm-jailbreak-prompt-injection-dataset","htb-ac-1424625/llm-prompt-injection-filtered-cyber","Den4ikAI/russian_instructions_2","eridai/russian_dpo_qa","attn-signs/russian-easy-instructions","aryashah00/multilingual-sycophancy","deepset/prompt-injections","neuralchemy/Prompt-injection-dataset","schis02/sycophancy-false-premises"]:
    R,info=rows(ds,1000)
    if not R: print(ds,"пусто"); continue
    txt=lambda r:" ".join(str(v) for v in r.values() if isinstance(v,str))
    ru=[r for r in R if RU.search(txt(r))]
    print(ds,"cols",info[0][:8],"total",info[1],"взято",len(R),"ru",len(ru),"JM",sum(1 for r in R if JM.search(txt(r))),"FM",sum(1 for r in R if FM.search(txt(r))))
    if ru: print("   пример:",txt(ru[0])[:160].replace("\n"," "))
PY
echo END
