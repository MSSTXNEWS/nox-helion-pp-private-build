#!/bin/bash
date -u +%T; echo health=$(curl -s -m 5 -o /dev/null -w "%{http_code}" http://127.0.0.1:8081/health)
tail -n 3 /root/nox/logs/flash.log | cut -c1-150; ls -l /dev/shm/glm53f/*00005* | cut -c20-90
ps -eo pid,etimes,args | grep -E "flash.py|llama-server" | grep -v grep | cut -c1-120
for f in /root/nox/logs/bench_*.log /root/nox/logs/glm_8081.log; do echo "== $f"; tail -n 8 $f 2>/dev/null | cut -c1-220; done
cat /root/nox/state/FLASH_SPEED.json 2>/dev/null | head -c 1200
nvidia-smi --query-gpu=memory.used --format=csv,noheader

# D2 read-only resource snapshot. No workload probes or host mutations.
echo '== NOX_D2_RESOURCE_SNAPSHOT_V1 =='
printf 'sample_utc='; date -u +%Y-%m-%dT%H:%M:%SZ
printf 'loadavg='; awk '{print $1, $2, $3}' /proc/loadavg
awk '/^MemTotal:|^MemAvailable:/ {printf "%s%s_KiB=%s", (NR==1?"":" "), substr($1,1,length($1)-1), $2} END {print ""}' /proc/meminfo
for k in memory.current memory.max memory.events cpu.stat; do
  p="/sys/fs/cgroup/$k"
  if [ -r "$p" ]; then
    printf 'cgroup_%s=' "$k"
    if [ "$k" = memory.events ] || [ "$k" = cpu.stat ]; then tr '\n' ';' < "$p"; printf '\n'; else cat "$p"; fi
  else
    printf 'cgroup_%s=unavailable\n' "$k"
  fi
done
for k in cpu memory io; do
  p="/proc/pressure/$k"
  if [ -r "$p" ]; then printf 'psi_%s=' "$k"; head -n 1 "$p"; else printf 'psi_%s=unavailable\n' "$k"; fi
done
df -P -B1 / 2>/dev/null | awk 'NR==2 {printf "root_bytes_total=%s root_bytes_used=%s root_bytes_available=%s\n", $2, $3, $4}'
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=index,memory.used,memory.free,memory.total,utilization.gpu --format=csv,noheader,nounits 2>/dev/null | awk -F, '{gsub(/[[:space:]]/, "", $0); printf "gpu_index=%s gpu_used_MiB=%s gpu_free_MiB=%s gpu_total_MiB=%s gpu_util_pct=%s\n", $1, $2, $3, $4, $5}'
else
  echo 'gpu_inventory=unavailable'
fi
