#!/bin/bash
# c78: безопасный тюнинг потоков DeepSeek + рестарт с автооткатом. STOP-флаги соблюдаются.
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-240; }
for s in /root/nox/STOP /root/nox/STOP.flag /root/nox/state/STOP /root/nox/state/STOP.flag; do [ -e $s ] && { echo "STOP $s -> exit"; exit 0; }; done
L=/root/nox/models/deepseek_v41_flash_iq2xxs/launch_ds41_8098_t119u.sh
echo "== launcher threads"; grep -nE "(^|[ \"])-t(b)?[ =]|THREADS|N_CPU_MOE|--threads" $L | a | head -8
[ -e $L.bak_c78 ] || cp $L $L.bak_c78
bench(){ python3 - <<'PY'
import json,time,urllib.request
body=json.dumps({"model":"x","messages":[{"role":"user","content":"Объясни простыми словами, что такое кэш процессора, в 5 предложениях."}],"max_tokens":96,"temperature":0,"stream":True}).encode()
req=urllib.request.Request("http://127.0.0.1:8098/v1/chat/completions",data=body,headers={"Content-Type":"application/json"})
t0=time.time();first=None;n=0;last=None
try:
  with urllib.request.urlopen(req,timeout=200) as r:
    for line in r:
        line=line.decode().strip()
        if line.startswith("data:") and not line.endswith("[DONE]"):
            d=json.loads(line[5:]);ch=d.get("choices") or []
            if ch and (ch[0].get("delta",{}).get("content") or ch[0].get("delta",{}).get("reasoning_content")):
                n+=1; last=time.time(); first=first or time.time()-t0
  print("ttft",round(first or -1,2),"tok_s",round(n/max(0.01,last-t0-first),2) if first else 0)
except Exception as e: print("bench ERR",e)
PY
}
echo "== before"; bench
if grep -qE "(^|[ \"])-t[ =]16|--threads[ =]16" $L; then
  sed -i -E 's/(^|[ "])-t[ =]16/\1-t 20/; s/(^|[ "])-tb[ =]16/\1-tb 40/; s/--threads[ =]16/--threads 20/; s/--threads-batch[ =]16/--threads-batch 40/' $L; echo "patched threads -> 20/40"; grep -nE "(^|[ \"])-t(b)?[ =][0-9]" $L | a | head -4
  supervisorctl restart nox-ds41-8098 2>&1 | a
  ok=0; for i in $(seq 1 60); do sleep 10; curl -s -m 3 localhost:8098/health | grep -q ok && { ok=1; break; }; done
  if [ $ok = 1 ]; then echo "model healthy after ~$((i*10))s"; echo "== after"; bench; bench
  else echo "UNHEALTHY -> rollback"; cp $L.bak_c78 $L; supervisorctl restart nox-ds41-8098 2>&1 | a; for i in $(seq 1 60); do sleep 10; curl -s -m 3 localhost:8098/health | grep -q ok && { echo "rolled back, healthy"; break; }; done; fi
else echo "pattern -t 16 not found in launcher; no change"; fi
curl -s -m 5 http://127.0.0.1:8091/api/health | cut -c1-160
