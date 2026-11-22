#!/bin/bash
D=/dev/shm/glm53f
echo "== dl"; pgrep -af "hf download" | cut -c1-80; du -sh $D; ls -l $D/*.gguf | awk '{printf "%.1f ГБ %s\n",$5/1073741824,$9}'; tail -c 300 /root/nox/logs/flash_dl.log
echo "== flash.py"; head -c 2500 /root/nox/flash.py
echo "== build"; ls -l /root/nox/llama.cpp-f/build/bin/llama-server; /root/nox/llama.cpp-f/build/bin/llama-server --version 2>&1 | head -2
echo "== cat state"; ls /root/nox/state | head; cat /root/nox/state/MODEL_SWAP.json 2>/dev/null | head -c 600
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
