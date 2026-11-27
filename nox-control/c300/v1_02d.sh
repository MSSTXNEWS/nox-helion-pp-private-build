echo "K1: v1_02d"
export RUNNER_TRACKING_ID=""
W=/workspace/nox
sed -n 470,530p $W/web/pkg/server/chat_core.py | cut -c1-230
echo "--- nox_mem llm ports"
grep -n -E "810[0-9]|8144|8141|8811|llama|openai|base_url|extract" $W/svc/mem/nox_mem.py | cut -c1-160 | head -25
echo "--- cold prefill test: baseline vs STOP of 30B"
python3 - <<'PY'
import json,time,http.client,os,signal,random
def call(sysm,slot,tag):
    b={"model":"x","messages":[{"role":"system","content":sysm},{"role":"user","content":"Привет"}],"stream":True,"max_tokens":4,"temperature":0.7,"cache_prompt":True,"id_slot":slot,"chat_template_kwargs":{"enable_thinking":False}}
    c=http.client.HTTPConnection("127.0.0.1",8104,timeout=90); t0=time.time(); c.request("POST","/v1/chat/completions",json.dumps(b).encode(),{"Content-Type":"application/json"}); r=c.getresponse(); tm=None
    for l in r:
        if l.startswith(b"data:"):
            d=l[5:].strip()
            if d==b"[DONE]": break
            j=json.loads(d); tm=j.get("timings") or tm
    tm=tm or {}; print(tag,"slot",slot,"prompt_n",tm.get("prompt_n"),"prompt_ms",round(tm.get("prompt_ms",0)),"tok/s",round(tm.get("prompt_per_second",0),1),"load",open("/proc/loadavg").read().split()[0])
def sysm(): return ("Ты NOX %d. "%random.randint(0,10**9))+"Обращайся к собеседнику «Создатель», отвечай по-русски. "*8
pids=[int(p) for p in os.popen("pgrep -f 'Thinking-2507'").read().split()]
for i in range(2): call(sysm(),i,"base")
st=[]
for p in pids:
    try: os.kill(p,signal.SIGSTOP); st.append(p)
    except Exception: pass
try:
    for i in range(2): call(sysm(),i+2,"stop30b")
finally:
    for p in st: os.kill(p,signal.SIGCONT)
print("stopped",len(st))
for i in range(2): call(sysm(),i,"base2")
PY
echo END
