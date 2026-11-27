echo "K1: v1_02c"
export RUNNER_TRACKING_ID=""
W=/workspace/nox
sed -n 409p $W/web/pkg/server/chat_core.py | cut -c200-700
echo "--- users of 8104 (grep)"
grep -rIl --include=*.py --include=*.sh --include=*.json -E "8104" $W/web $W/ops $W/agent $W/living $W/mem* $W/s03* 2>/dev/null | head -25
echo "--- conns to 8104"
ss -tnp 2>/dev/null | grep ":8104 " | awk '{print $1,$5,$6}' | sed -E 's/users:\(\("([^"]*)",pid=([0-9]+).*/\1 \2/' | sort | uniq -c | head -15
echo "--- 18220 owner"
P=$(ss -ltnp 2>/dev/null | grep ":18220 " | grep -oE 'pid=[0-9]+' | head -1 | cut -d= -f2); echo pid=$P; tr '\0' ' ' < /proc/$P/cmdline | cut -c1-200; echo
ls -l /proc/$P/cwd 2>/dev/null | awk '{print $NF}'
echo "--- direct 8104 timings"
python3 - <<'PY'
import json,time,http.client,sys
sys.path.insert(0,"/workspace/nox/web/pkg/server")
SYS="Ты NOX, тёплый ассистент. Обращайся к собеседнику «Создатель». "*6
def call(msgs,slot,tag):
    b={"model":"x","messages":msgs,"stream":True,"max_tokens":12,"temperature":0.7,"cache_prompt":True,"chat_template_kwargs":{"enable_thinking":False}}
    if slot is not None: b["id_slot"]=slot
    c=http.client.HTTPConnection("127.0.0.1",8104,timeout=60); t0=time.time(); c.request("POST","/v1/chat/completions",json.dumps(b).encode(),{"Content-Type":"application/json"}); r=c.getresponse(); first=None; tm=None
    for l in r:
        if not l.startswith(b"data:"): continue
        d=l[5:].strip()
        if d==b"[DONE]": break
        j=json.loads(d)
        if first is None and ((j.get("choices") or [{}])[0].get("delta") or {}).get("content"): first=time.time()-t0
        if j.get("timings"): tm=j["timings"]
    tm=tm or {}
    print(tag,"slot",slot,"ttft",None if first is None else round(first,2),"prompt_n",tm.get("prompt_n"),"cache_n",tm.get("cache_n"),"prompt_ms",round(tm.get("prompt_ms",0)),"pred_tps",round(tm.get("predicted_per_second",0),1))
base=[{"role":"system","content":SYS}]
for i in range(3): call(base+[{"role":"user","content":"Привет %d, как дела?"%i}],None,"auto")
for i in range(3): call(base+[{"role":"user","content":"Расскажи про погоду %d"%i}],0,"slot0")
for s in (1,2,3,0): call(base+[{"role":"user","content":"Расскажи про погоду 9"}],s,"rot")
PY
echo "LOAD $(cut -d' ' -f1 /proc/loadavg)"
echo END
