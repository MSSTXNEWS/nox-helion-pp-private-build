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
*) echo unknown;;
esac
