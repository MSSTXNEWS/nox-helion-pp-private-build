#!/bin/bash
# gpu_tier: команды из CMD (отдельно от block1). Вывод короткий.
gh_raw(){ curl -fsSL -H "Accept: application/vnd.github.raw" "https://api.github.com/repos/MSSTXNEWS/nox-helion-pp-private-build/contents/nox-control/gpu_tier/$1?ref=main"; }
CMD="$(gh_raw CMD | tr -d '[:space:]')"
echo "CMD=$CMD"
case "$CMD" in
recon)
  nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv,noheader
  nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader
  pgrep -af llama-server | cut -c1-400
  ls -la /root/nox/models /root/nox/llama.cpp/build/bin 2>/dev/null | grep -Ei "gguf|llama-server|llama-bench" | cut -c1-150
  find / -name "*.gguf" -size +100M -not -path "/dev/shm/*" 2>/dev/null | head -10
  ls -la /dev/shm/nox_glm | tail -14
  pgrep -af "curl|redo" | cut -c1-120 | head -4
  free -g | head -2; nproc; lscpu | grep -E "Model name|Socket|Thread|Core|NUMA node\(s\)"
  df -h /root | tail -1
  ls /root/nox/scripts | head -40; ls /root/nox/run 2>/dev/null | head
  curl -s -m3 localhost:8083/health; curl -s -m3 localhost:8082/health | head -c 150
  ;;
recon2)
  nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv,noheader
  pgrep -af "llama-server" | grep -v pgrep | cut -c1-500
  cd /root/nox/llama.cpp && git log -1 --format='%h %cd' 2>/dev/null; ls build/bin | head -20
  for r in unsloth/Qwen3.5-9B-GGUF unsloth/Qwen3.5-4B-GGUF unsloth/Qwen3.5-27B-GGUF; do echo "== $r"; curl -s -m15 "https://huggingface.co/api/models/$r/tree/main" | python3 -c 'import sys,json;[print(x["path"],x.get("size")) for x in json.load(sys.stdin) if "Q4_K_M" in x["path"] or "Q4_K_XL" in x["path"] or "mmproj" in x["path"]]' 2>&1 | head -6; done
  ls /root/nox/dl/hf /root/nox/models 2>/dev/null | head; ls /root/s2_backup* 2>/dev/null | head -5
  ;;
fast9b)
  D=/root/nox/dl/hf/qwen35_9b; F=$D/Qwen3.5-9B-Q4_K_M.gguf; LG=/root/nox/logs; BIN=/root/nox/llama.cpp/build/bin/llama-server
  U=https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/main/Qwen3.5-9B-Q4_K_M.gguf
  mkdir -p $D
  SZ=$(curl -sIL -m20 "$U" | tr -d '\r' | awk 'tolower($1)=="content-length:"{v=$2} END{print v}')
  CUR=$(stat -c %s $F 2>/dev/null || echo 0); echo "size remote=$SZ local=$CUR"
  if [ -n "$SZ" ] && [ "$CUR" -lt "$SZ" ]; then
    pgrep -f "qwen35_9b.*curl|curl.*Qwen3.5-9B" >/dev/null || nohup setsid curl -fL -C - --retry 5 -o $F "$U" > $LG/dl_qwen35.log 2>&1 < /dev/null &
    sleep 60; echo "dl now $(stat -c %s $F)"; exit 0
  fi
  pgrep -f "port 8084" >/dev/null && pkill -f "port 8084"; sleep 1
  nohup setsid $BIN -m $F --host 127.0.0.1 --port 8084 -c 12288 -ngl 99 -fa on --parallel 2 --jinja --chat-template-kwargs '{"enable_thinking":false}' --reasoning-budget 0 > $LG/fast9b_test.log 2>&1 < /dev/null &
  for i in $(seq 1 40); do curl -s -m2 localhost:8084/health | grep -q ok && break; sleep 3; done
  tail -n 3 $LG/fast9b_test.log | cut -c1-200
  nvidia-smi --query-gpu=memory.used --format=csv,noheader
  cat > /tmp/bench.py <<'P'
import json,sys,time,urllib.request
port=sys.argv[1]
def run(msg,n=120):
    b={"model":"fast","messages":[{"role":"system","content":"Ты NOX HELION. Отвечай по-русски коротко."},{"role":"user","content":msg}],"max_tokens":n,"stream":True,"temperature":0.7}
    t=time.time();r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:%s/v1/chat/completions"%port,json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=60)
    first=None;k=0;txt=""
    for l in r:
        l=l.decode()
        if l.startswith("data: {"):
            d=json.loads(l[6:])["choices"][0]["delta"]; c=d.get("content") or ""
            if c:
                if first is None:first=time.time()-t
                k+=1;txt+=c
    tot=time.time()-t
    return first,k/max(tot-(first or 0),1e-6),txt[:80].replace("\n"," ")
run("привет",5)
for m in ("Привет, кто ты?","Объясни разницу между TCP и UDP в трёх предложениях.","Напиши план проверки сервера на 5 пунктов."):
    f,tps,t=run(m); print("TTFT=%.2fs tps=%.1f | %s"%(f,tps,t))
P
  python3 /tmp/bench.py 8084
  echo "--old 4B:"; python3 /tmp/bench.py 8083 | tail -2
  ;;
swap)
  F=/root/nox/dl/hf/qwen35_9b/Qwen3.5-9B-Q4_K_M.gguf; LG=/root/nox/logs; BIN=/root/nox/llama.cpp/build/bin/llama-server
  mkdir -p /root/nox/gpu_tier
  cat > /root/nox/gpu_tier/fast_start.sh <<'P'
#!/bin/bash
# быстрый тир: Qwen3.5-9B Q4_K_M целиком на GPU, без размышлений, порт 8083
pkill -f "port 8083"; pkill -f "port 8084"; sleep 2
exec setsid /root/nox/llama.cpp/build/bin/llama-server -m /root/nox/dl/hf/qwen35_9b/Qwen3.5-9B-Q4_K_M.gguf --host 127.0.0.1 --port 8083 -c 12288 -ngl 99 -fa on --parallel 2 --jinja --chat-template-kwargs '{"enable_thinking":false}' --reasoning-budget 0 >> /root/nox/logs/fast_server.log 2>&1 < /dev/null
P
  chmod +x /root/nox/gpu_tier/fast_start.sh
  nohup setsid /root/nox/gpu_tier/fast_start.sh > /dev/null 2>&1 < /dev/null &
  for i in $(seq 1 40); do curl -s -m2 localhost:8083/health | grep -q ok && break; sleep 3; done
  pgrep -af llama-server | cut -c1-150; nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
  python3 /tmp/bench.py 8083 | tail -3
  echo "--gateway fast:"
  curl -s -m60 localhost:8082/v1/chat/completions -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"Кто ты и что умеешь? Одной фразой."}],"nox_mode":"fast","max_tokens":80}' | head -c 500; echo
  curl -s -m5 localhost:8082/v1/nox/stats | head -c 300
  ;;
log) pgrep -af llama-server | cut -c1-160; tail -n 15 /root/nox/logs/fast_server.log | cut -c1-200; nvidia-smi --query-gpu=memory.used --format=csv,noheader;;
bench)
  python3 /tmp/bench.py 8083 | tail -3
  curl -s -m60 localhost:8082/v1/chat/completions -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"Кто ты? Одной фразой."}],"nox_mode":"fast","max_tokens":60}' | head -c 400; echo
  curl -s -m5 localhost:8081/health; echo; tail -n 3 /root/nox/logs/glm_server.log | cut -c1-200; free -g | sed -n 2p; nvidia-smi --query-gpu=memory.used --format=csv,noheader;;
glmstate)
  ls -la /dev/shm/nox_glm | awk '{print $5,$9}' | tail -12; ls -la /root/nox/glm53_disk /root/nox/glm53 2>/dev/null | awk '{print $5,$9}' | tail -6
  pgrep -af "curl|redo|llama" | cut -c1-130 | head -5
  grep -E " E |error|failed|alloc|CUDA|out of memory" /root/nox/logs/glm_server.log | cut -c1-220 | tail -8
  nvidia-smi --query-gpu=memory.used --format=csv,noheader;;
glmstart|glmbench)
  mkdir -p /root/nox/gpu_tier; LG=/root/nox/logs
  cat > /root/nox/gpu_tier/glm_start.sh <<'P'
#!/bin/bash
# GLM-5.3 гибрид: внимание+KV+общий эксперт на GPU, маршрутизируемые эксперты в RAM. Только mmap (без --no-mmap/--mlock), KV f16.
ARGS="$(cat /root/nox/gpu_tier/glm.args 2>/dev/null)"
pkill -f "port 8081"; sleep 3
exec setsid /root/nox/llama.cpp/build/bin/llama-server -m /root/nox/glm53/GLM-5.3-UD-Q4_K_XL-00001-of-00011.gguf --host 127.0.0.1 --port 8081 $ARGS >> /root/nox/logs/glm_server.log 2>&1 < /dev/null
P
  chmod +x /root/nox/gpu_tier/glm_start.sh
  cat > /root/nox/gpu_tier/bench_glm.py <<'P'
import json,time,urllib.request
def comp(p,n):
    b={"prompt":p,"n_predict":n,"cache_prompt":False,"temperature":0,"stream":False}
    t=time.time();r=json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8081/completion",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=900))
    tm=r["timings"];return tm["prompt_n"],tm["prompt_per_second"],tm["predicted_n"],tm["predicted_per_second"],time.time()-t
long=("Сервер обрабатывает запросы пользователей и пишет журнал. "*70)
print("warm",comp("Привет",8)[3:])
print("short prefill_n=%d pp=%.1f t/s | decode n=%d tg=%.2f t/s | %.1fs"%comp("Объясни кратко, что такое RAID.",48))
print("long  prefill_n=%d pp=%.1f t/s | decode n=%d tg=%.2f t/s | %.1fs"%comp(long+" Кратко:",32))
P
  if [ "$CMD" = glmstart ]; then
    GLM_ARGS="$(gh_raw GLM_ARGS 2>/dev/null)"
    [ -n "$GLM_ARGS" ] || GLM_ARGS='-c 16384 -ngl 99 -ot exps=CPU -t 24 -tb 24 -fa on --parallel 1 -b 512 -ub 256 --jinja --temp 1.0 --top-p 0.95 --min-p 0.01'
    echo "$GLM_ARGS" > /root/nox/gpu_tier/glm.args; echo "args: $GLM_ARGS"
    : > /root/nox/logs/glm_server.log
    nohup setsid /root/nox/gpu_tier/glm_start.sh > /dev/null 2>&1 < /dev/null &
    sleep 90
  fi
  curl -s -m3 localhost:8081/health; echo; grep -E "offload|CUDA0 .*buffer|KV|failed|error" /root/nox/logs/glm_server.log | cut -c1-200 | tail -8
  tail -n 2 /root/nox/logs/glm_server.log | cut -c1-200; nvidia-smi --query-gpu=memory.used --format=csv,noheader; nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader; free -g | sed -n 2p
  if [ "$CMD" = glmbench ] && curl -s -m3 localhost:8081/health | grep -q ok; then pgrep -f bench_glm.py >/dev/null || (nohup setsid python3 /root/nox/gpu_tier/bench_glm.py > /root/nox/logs/glm_bench.out 2>&1 < /dev/null &); sleep 100; vmstat 1 3 | tail -2; cat /proc/pressure/io 2>/dev/null | head -1; cat /root/nox/logs/glm_bench.out | tail -5; fi
  ;;
glmlog)
  L=/root/nox/logs/glm_server.log
  grep -E "n_layer|n_expert|n_embd |n_ff|n_head|file size|model params|n_ctx_train|arch |expert_used|override|nextn|dsa|indexer" $L | cut -c1-170 | head -24
  grep -c "buffer type overrides\|overriding" $L; grep -E "assigned|CPU_Mapped|CUDA0 model buffer|offloading" $L | cut -c1-170 | head -8
  ;;
tier4b)
  pkill -f "port 8083"; sleep 3
  nohup setsid /root/nox/llama.cpp/build/bin/llama-server -m /root/nox/dl/hf/qwen3_4b/Qwen3-4B-Instruct-2507-Q4_K_M.gguf --host 127.0.0.1 --port 8083 -c 8192 -ngl 99 -fa on --parallel 2 --jinja >> /root/nox/logs/fast_server.log 2>&1 < /dev/null &
  for i in $(seq 1 30); do curl -s -m2 localhost:8083/health | grep -q ok && break; sleep 3; done
  curl -s -m3 localhost:8083/health; nvidia-smi --query-gpu=memory.used --format=csv,noheader; nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader
  pgrep -af llama-server | cut -c1-120; free -g | sed -n 2p; uptime
  ;;
gw)
  tail -n 4 /root/nox/logs/glm_bench.out
  curl -s -m5 localhost:8082/health | head -c 150; echo
  for M in fast deep; do echo "== $M"; curl -sN -m 100 localhost:8082/v1/chat/completions -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"Объясни в двух предложениях, чем RAID1 отличается от RAID5."}],"nox_mode":"'$M'","stream":true,"max_tokens":60}' | python3 -c '
import sys,json,time
t=time.time();st={}
for l in sys.stdin:
    if l.startswith("data: {"):
        d=json.loads(l[6:]);ch=d.get("choices") or [{}]
        dl=ch[0].get("delta",{});c=dl.get("content")
        if c:
            s=dl.get("nox_stage","?");st.setdefault(s,[round(time.time()-t,2),""]);st[s][1]+=c
        if d.get("nox") and ch[0].get("finish_reason"): print("final",json.dumps(d["nox"],ensure_ascii=False)[:300])
for k,v in st.items(): print(k,"first@",v[0],"|",v[1][:150].replace("\n"," "))
' ; done
  ;;
bstart) nohup setsid python3 /root/nox/gpu_tier/bench_glm.py > /root/nox/logs/glm_bench.out 2>&1 < /dev/null & sleep 2; ps aux | grep -c "[b]ench_glm" ;;
bshow) cat /root/nox/logs/glm_bench.out; ps aux | grep -c "[b]ench_glm"; top -bn1 | head -12 | tail -6; vmstat 1 2 | tail -1;;
diag)
  cat /root/nox/logs/glm_bench.out; cat /sys/fs/cgroup/cpu.max /sys/fs/cgroup/cpu.stat 2>/dev/null | head -8
  P=$(pgrep -f "port 8081" | head -1); taskset -cp $P; grep -E "Cpus_allowed_list|Threads" /proc/$P/status
  top -H -bn1 -p $P | head -16 | tail -10
  nvidia-smi --query-gpu=utilization.gpu,clocks.sm,pcie.link.gen.current,pcie.link.width.current --format=csv,noheader
  grep -E "n_threads|threadpool|cpu_moe|op_offload|offload" /root/nox/logs/glm_server.log | cut -c1-160 | head -5
  ;;
ab)
  A="$(gh_raw GLM_ARGS)"; echo "args: $A"; echo "$A" > /root/nox/gpu_tier/glm.args
  sed -i 's/\*70/*35/' /root/nox/gpu_tier/bench_glm.py
  pkill -f bench_glm; : > /root/nox/logs/glm_server.log
  nohup setsid /root/nox/gpu_tier/glm_start.sh > /dev/null 2>&1 < /dev/null &
  for i in $(seq 1 60); do curl -s -m2 localhost:8081/health | grep -q ok && break; sleep 3; done
  curl -s -m2 localhost:8081/health; echo; nvidia-smi --query-gpu=memory.used --format=csv,noheader
  nohup setsid python3 /root/nox/gpu_tier/bench_glm.py > /root/nox/logs/glm_bench.out 2>&1 < /dev/null &
  for i in $(seq 1 60); do grep -q "^long" /root/nox/logs/glm_bench.out && break; sleep 3; done
  cat /root/nox/logs/glm_bench.out
  ;;
glmlog2) pgrep -af "llama-server|python" | cut -c1-140; tail -n 8 /root/nox/logs/glm_server.log | cut -c1-220; curl -s -m2 localhost:8081/health; nvidia-smi --query-gpu=memory.used --format=csv,noheader; uptime;;
sweep)
  ls -t /root/nox/logs | grep -i -E "sweep|ik|bench" | head -6
  head -c 1500 /root/nox/glm_sweep.py | head -30
  for f in $(ls -t /root/nox/logs/*sweep* 2>/dev/null | head -2); do echo "## $f"; tail -n 25 $f | cut -c1-230; done
  pgrep -af "glm_sweep|ik_llama" | cut -c1-260; curl -s -m2 localhost:8081/health
  ;;
*) echo unknown;;
esac
