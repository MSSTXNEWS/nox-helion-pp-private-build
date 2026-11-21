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
*) echo unknown;;
esac
