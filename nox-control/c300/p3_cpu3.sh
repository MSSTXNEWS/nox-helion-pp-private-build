#!/bin/bash
echo "load $(cut -d' ' -f1-3 /proc/loadavg)"; free -m | head -2; vmstat 1 3 | tail -2
echo "== PSI"; cat /proc/pressure/memory /proc/pressure/io /proc/pressure/cpu 2>&1 | head -6
echo "== 8104 full cmd"; tr '\0' ' ' </proc/$(pgrep -f 'port 8104'|head -1)/cmdline | sed -E 's/(--api-key|--key)[ =][^ ]+/\1 ***/g'; echo
echo "== 8104 health/slots"; curl -s -m 5 127.0.0.1:8104/health; echo; curl -s -m 5 127.0.0.1:8104/slots | python3 -c "import sys,json
try:
 for s in json.load(sys.stdin): print({k:s.get(k) for k in ('id','is_processing','n_ctx','id_task')})
except Exception as e: print('slots',e)"
echo "== established conns to 8104"; ss -Htn state established '( dport = :8104 )' | wc -l
echo "== swap cfg 8104 refs"; grep -n -B2 -A8 "8104" /workspace/nox/serve/llama-swap.yaml | cut -c1-260 | head -40
echo "== who calls 8104 (clients)"; ss -Htnp state established '( dport = :8104 )' | awk '{print $4}' | sort | uniq -c | head; 
echo "== top 20s threads"; top -H -b -d 20 -n 2 -w 180 | awk '/^top -/{n++} n>=2' | awk '($9+0)>=20' | cut -c1-150 | head -25
echo "== chat via web :8091"; curl -s -m 5 -o /dev/null -w "root %{http_code}\n" 127.0.0.1:8091/ ; curl -s -m 5 127.0.0.1:8091/api/health | head -c 200; echo
python3 - <<'PY'
import json,time,http.client
t=time.time();c=http.client.HTTPConnection("127.0.0.1",8091,timeout=100)
c.request("POST","/api/chat",json.dumps({"messages":[{"role":"user","content":"Привет! Одним предложением: как дела?"}],"stream":True}),{"Content-Type":"application/json"})
r=c.getresponse();print("status",r.status,round(time.time()-t,2));ft=None;n=0;buf=b""
while True:
    l=r.readline()
    if not l:break
    n+=1
    if ft is None and b'"delta"' in l: ft=time.time()-t
    if n<6: print(l[:160])
print("first_delta_s",ft and round(ft,2),"total_s",round(time.time()-t,1),"lines",n)
PY
