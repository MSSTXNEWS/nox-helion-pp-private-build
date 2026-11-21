#!/bin/bash
echo "== dl"; grep -E "ok|->|DONE" /root/nox/logs/glm_dl.log | tail -12; du -sh /dev/shm/nox_glm /root/nox/glm53_disk 2>/dev/null; df -h /dev/shm | tail -1; pgrep -c curl
echo "== build"; tail -4 /root/nox/logs/build_llama.log 2>/dev/null
echo "== mem"; free -g | head -2
