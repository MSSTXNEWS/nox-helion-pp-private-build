#!/bin/bash
# READ-ONLY: что на S2 ценно для переноса на новую модель, размеры
cd /root/nox 2>/dev/null || exit 1
echo "== top"; du -sh --max-depth=1 /root/nox 2>/dev/null | sort -rh | head -22
echo "== state"; du -sh --max-depth=1 /root/nox/state 2>/dev/null | sort -rh | head -14
echo "== lora/adapters"; find /root/nox -maxdepth 4 \( -name "adapter_model*" -o -name "*.safetensors" \) -size +1M 2>/dev/null | head -8 | xargs -r du -sh
echo "== memory/knowledge"; for d in memory knowledge datasets lora state/memory state/NOX_SELF_T186U; do [ -e /root/nox/$d ] && du -sh /root/nox/$d; done
echo "== gguf"; find / -xdev -name "*.gguf" -size +1G 2>/dev/null | xargs -r du -sh | head
echo "== disk"; df -h / | tail -1
