#!/bin/bash
# gpu_tier: команды из CMD (отдельно от block1). Вывод короткий.
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/gpu_tier
CMD="$(curl -fsSL "$R/CMD?t=$RANDOM" | tr -d '[:space:]')"
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
*) echo unknown;;
esac
