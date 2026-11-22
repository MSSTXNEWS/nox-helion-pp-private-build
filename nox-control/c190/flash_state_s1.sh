#!/bin/bash
echo "== shm/диск"; df -h /dev/shm / | tail -2; du -sh /dev/shm/glm53f 2>/dev/null; ls /dev/shm | head; free -g | sed -n 2p
echo "== загрузки/сборки"; ps -eo pid,etimes,pcpu,args | grep -E "hf |huggingface|hf_transfer|make|cmake|nvcc|llama-server|llama.cpp-f" | grep -v grep | sed -E 's/ -(c|b|ub|fa|np|t|tb|amb) .*//' | cut -c1-200
echo "== flash файлы"; find /dev/shm /root/nox -maxdepth 3 \( -iname "*flash*" -o -name "glm53f" -o -name "llama.cpp-f" \) 2>/dev/null | head; ls -la /dev/shm/glm53f 2>/dev/null | head -20
echo "== hf"; (hf version || huggingface-cli version) 2>&1 | head -2; pip list 2>/dev/null | grep -iE "hf.transfer|huggingface"
nproc; ls /root/nox/logs | grep -iE "flash|glm53f|llama_f" | head
