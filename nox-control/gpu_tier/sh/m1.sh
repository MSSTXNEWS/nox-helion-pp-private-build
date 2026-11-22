echo "== M1 measure"
pgrep -f run_all_tests >/dev/null && echo tests_running
P=$(pgrep -f "llama-server.*--port 8081" | head -1); echo pid $P
numactl -H 2>&1 | head -8 | cut -c1-120
numastat -p $P 2>&1 | tail -8 | cut -c1-120
cat /sys/kernel/mm/transparent_hugepage/enabled; grep -E "AnonHugePages" /proc/$P/smaps_rollup
nvidia-smi --query-gpu=pcie.link.gen.current,pcie.link.gen.max,pcie.link.width.current,memory.used --format=csv,noheader
grep -E "offloaded|CUDA0 model buffer|CPU_Mapped model|KV buffer|compute buffer" /root/nox/logs/glm_8081.log | cut -c1-140 | head -6
cat > /tmp/gen.py <<'P'
import json,urllib.request,time
def c(p,n):
    b={"prompt":p,"n_predict":n,"cache_prompt":False,"temperature":0}
    r=json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8081/completion",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=280))["timings"]
    print("pp %.1f (n=%d) tg %.2f (n=%d)"%(r["prompt_per_second"],r["prompt_n"],r["predicted_per_second"],r["predicted_n"]),flush=True)
c("Объясни кратко, что такое RAID, и чем RAID5 отличается от RAID10.",90)
P
(nvidia-smi dmon -s t -c 40 -d 1 > /tmp/dmon.txt 2>&1; ) &
(mpstat -P ALL 5 5 > /tmp/mp.txt 2>&1) &
python3 /tmp/gen.py
wait
echo "PCIe dmon (rx/tx MB/s) max/avg:"; awk '$1 ~ /^[0-9]/ {r+=$2;t+=$3;n++; if($2>mr)mr=$2; if($3>mt)mt=$3} END{print "rx avg",r/n,"max",mr,"tx avg",t/n,"max",mt}' /tmp/dmon.txt
grep Average /tmp/mp.txt | awk '$2!="CPU"{u=100-$NF; if(u>50)hi++; s+=u; n++} END{print "cpu avg%",s/n,"cores>50%:",hi,"of",n-1}'
nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader
