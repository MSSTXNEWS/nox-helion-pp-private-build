#!/bin/bash
cat /root/nox/start_glm.sh | head -40
echo ---; ls /root/nox/llama.cpp-f/build/bin 2>/dev/null | tr '\n' ' '; ls /dev/shm/glm53f | head -20
echo ---; nvidia-smi --query-gpu=name,memory.used,memory.total --format=csv,noheader; free -g | head -2
echo ---; cd /root/nox/llama.cpp-f && git log --oneline -2 2>&1 | head -2; grep -rl "nextn\|mtp" src/llama-arch.cpp 2>/dev/null | head -2; grep -n "spec" common/arg.cpp | grep -E '"--(spec|draft|model-draft)[a-z-]*"' | head -8
echo ---; curl -s localhost:8081/props | head -c 400; echo; curl -s localhost:8081/slots | head -c 300
echo ---; ls /root/nox/*.gguf /root/nox/models 2>/dev/null | head; pgrep -af llama-server | cut -c1-300
