#!/bin/bash
export HF_HUB_ENABLE_HF_TRANSFER=1
pip install -q -U hf_transfer --break-system-packages 2>&1 | tail -1
D=/dev/shm/glm53f
if pgrep -f "hf download unsloth/GLM-5.3-Flash" >/dev/null; then echo "уже качает"; else
 nohup setsid hf download unsloth/GLM-5.3-Flash-GGUF --include "*UD-Q4_K_XL*" --local-dir $D > /root/nox/logs/flash_dl.log 2>&1 < /dev/null &
 echo "запущена докачка"; fi
S0=$(du -sb $D | cut -f1); sleep 25; S1=$(du -sb $D | cut -f1)
echo "скорость МБ/с: $(( (S1-S0)/25/1048576 ))  всего ГБ: $((S1/1073741824))"
ls -l $D | awk '{print $5/1073741824" ГБ", $9}' | tail -8
tail -3 /root/nox/logs/flash_dl.log | cut -c1-200
echo "== сборка"; tail -5 /root/nox/logs/flash_build.log | cut -c1-200; ls -d /root/nox/llama.cpp-f* /root/nox/*flash* 2>/dev/null; ls /root/nox | head -30
