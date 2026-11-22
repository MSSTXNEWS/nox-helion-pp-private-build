#!/bin/bash
date -u +%H:%M:%S
echo "== flash.py proc"; ps -eo pid,etimes,args | grep -E "flash.py|flash_" | grep -v grep | cut -c1-150
echo "== log tail"; tail -n 8 /root/nox/logs/flash.log | cut -c1-220
echo "== dirs"; du -sh /dev/shm/glm53f/.cache /dev/shm/glm53f/UD-Q4_K_XL /dev/shm/glm53f/Shard_Rewrite 2>/dev/null; ls /dev/shm/glm53f/UD-Q4_K_XL | head -3; ls -l /dev/shm/glm53f/*.gguf | awk '{printf "%.2f %s\n",$5/1073741824,$9}'
echo "== ports"; for p in 8081 8083 8082; do echo "$p $(curl -s -m 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:$p/health)"; done
