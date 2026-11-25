#!/bin/bash
# P3 cpu audit, read-only (60s sampling)
echo "== host"; nproc; lscpu | grep -E "Model name|Socket|Core\(s\)|Thread|NUMA|^CPU\(s\)"; cat /proc/loadavg
echo "== cgroup"; cat /sys/fs/cgroup/cpuset.cpus.effective /sys/fs/cgroup/cpu.max 2>&1 | head -3; cat /sys/fs/cgroup/cpu/cpu.cfs_quota_us 2>/dev/null
echo "== top threads 60s (3 samples)"
top -H -b -d 20 -n 4 -w 200 2>/dev/null | awk '/^top -/{n++} n>=2' | grep -vE "^\s*$" | awk 'NR<=0 || ($9+0)>=15 || /^top|Cpu\(s\)/' | cut -c1-170 | head -70
echo "== per-process CPU (ps, cumulative sample 30s)"
ps -eo pid,pcpu,nlwp,ni,rss,etimes,psr,args --sort=-pcpu 2>/dev/null | sed -E 's/(--api-key|--master-key|-k|--key|--token)[ =][^ ]+/\1 ***/g; s/(key|token|secret)=[^ ]+/\1=***/Ig' | cut -c1-230 | head -45
echo "== pidstat"; which pidstat mpstat >/dev/null 2>&1 && pidstat -u -h 20 1 2>/dev/null | sort -k8 -nr | head -25 | cut -c1-200
echo "== llama-server flags + affinity"
for p in $(pgrep -f llama-server); do echo "pid $p aff=$(taskset -cp $p 2>/dev/null | sed 's/.*: //') ni=$(ps -o ni= -p $p) thr=$(ls /proc/$p/task | wc -l) cpu=$(ps -o pcpu= -p $p)"; tr '\0' ' ' < /proc/$p/cmdline | sed -E 's/(--api-key|--key)[ =][^ ]+/\1 ***/g' | cut -c1-400; echo; done
echo "== other key procs affinity"
for pat in distill_v2 judge_service web_server arbiter embed_server playwright chromium llama-swap invokeai; do for p in $(pgrep -f "$pat" | head -4); do echo "$pat pid $p aff=$(taskset -cp $p 2>/dev/null | sed 's/.*: //') ni=$(ps -o ni= -p $p) cpu=$(ps -o pcpu= -p $p) thr=$(ls /proc/$p/task 2>/dev/null| wc -l)"; done; done
echo "== chrome count"; pgrep -fc "chrom" ; pgrep -fc playwright
echo "== old tail -f / loops"; ps -eo pid,etimes,args | grep -E "tail -f|watch |sleep [0-9]{3,}|while true" | grep -v grep | cut -c1-160 | head -15
echo "== web port"; for p in $(pgrep -f web_server.py); do ss -ltnp 2>/dev/null | grep "pid=$p," | awk '{print $4}'; done
echo "== arbiter"; ls /workspace/nox/ops/*/arbiter.py 2>/dev/null; find /workspace/nox -maxdepth 3 -name arbiter.py 2>/dev/null | head -3
echo "== swap cfg"; ls /workspace/nox/ops/ 2>/dev/null | head -40; find /workspace/nox -maxdepth 3 \( -name "llama-swap*.y*ml" -o -name "swap*.yaml" -o -name config.yaml \) 2>/dev/null | head
echo "== baseline chat 8104 stream"
python3 - <<'PY'
import json,time,http.client
t=time.time();c=http.client.HTTPConnection("127.0.0.1",8104,timeout=120)
c.request("POST","/v1/chat/completions",json.dumps({"messages":[{"role":"user","content":"Привет, расскажи кратко о Севастополе."}],"max_tokens":80,"stream":True}),{"Content-Type":"application/json"})
r=c.getresponse();ft=None;n=0
while True:
    l=r.readline()
    if not l:break
    if l.startswith(b"data:") and b'"content"' in l and b'"content":""' not in l:
        n+=1
        if ft is None: ft=time.time()-t
print("8104 status",r.status,"first_token_s",ft,"total_s",round(time.time()-t,1),"chunks",n)
PY
