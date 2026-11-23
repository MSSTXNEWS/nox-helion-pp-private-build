#!/bin/bash
date -u +%T; echo health=$(curl -s -m 5 -o /dev/null -w "%{http_code}" http://127.0.0.1:8081/health)
tail -n 3 /root/nox/logs/flash.log | cut -c1-150; ls -l /dev/shm/glm53f/*00005* | cut -c20-90
ps -eo pid,etimes,args | grep -E "flash.py|llama-server" | grep -v grep | cut -c1-120
for f in /root/nox/logs/bench_*.log /root/nox/logs/glm_8081.log; do echo "== $f"; tail -n 8 $f 2>/dev/null | cut -c1-220; done
cat /root/nox/state/FLASH_SPEED.json 2>/dev/null | head -c 1200
# One bounded NVML probe for legacy used-only and detailed telemetry.
# A stalled GPU driver must not stall the owner readback; unknown is never admission.
gpu_rows=''
if command -v nvidia-smi >/dev/null 2>&1 && command -v timeout >/dev/null 2>&1; then
  gpu_rows=$(timeout -k 1s 4s nvidia-smi --query-gpu=index,memory.used,memory.free,memory.total,utilization.gpu --format=csv,noheader,nounits 2>/dev/null) || gpu_rows=''
fi
# Validate the entire GPU snapshot before publishing ANY capacity number.
# A partial or contradictory NVML response must not be mistaken for admission.
if [ -n "$gpu_rows" ]; then
  gpu_rows=$(printf '%s\n' "$gpu_rows" | awk -F, '
    NF != 5 {bad=1; next}
    {
      for (i=1; i<=5; i++) {
        gsub(/[[:space:]]/, "", $i)
        if ($i !~ /^[0-9]+$/) bad=1
      }
      if (seen[$1]++ || $5+0 > 100 || $2+$3 > $4) bad=1
      lines[++n]=$1 "," $2 "," $3 "," $4 "," $5
    }
    END {
      if (bad || n == 0) exit 1
      for (i=1; i<=n; i++) print lines[i]
    }') || gpu_rows=''
fi
if [ -n "$gpu_rows" ]; then
  printf '%s\n' "$gpu_rows" | awk -F, '{print $2 " MiB"}'
else
  echo 'gpu_memory_used=unavailable'
fi

# D2 read-only resource snapshot. No workload probes or host mutations.
echo '== NOX_D2_RESOURCE_SNAPSHOT_V1 =='
printf 'sample_utc='; date -u +%Y-%m-%dT%H:%M:%SZ
printf 'loadavg='; awk '{print $1, $2, $3}' /proc/loadavg
# Bounded 1s host CPU sample: host-wide busy percentage, not cgroup quota admission.
if [ -r /proc/stat ]; then
  read -r _ u1 n1 s1 i1 w1 irq1 sirq1 steal1 rest1 < /proc/stat
  sleep 1
  read -r _ u2 n2 s2 i2 w2 irq2 sirq2 steal2 rest2 < /proc/stat
  if [[ "$u1" =~ ^[0-9]+$ && "$u2" =~ ^[0-9]+$ && "$steal1" =~ ^[0-9]+$ && "$steal2" =~ ^[0-9]+$ ]]; then
    dtotal=$((u2+n2+s2+i2+w2+irq2+sirq2+steal2-u1-n1-s1-i1-w1-irq1-sirq1-steal1))
    didle=$((i2+w2-i1-w1))
    if (( dtotal > 0 && didle >= 0 && didle <= dtotal )); then
      cpu_tenths=$(((dtotal-didle)*1000/dtotal))
      printf 'host_cpu_busy_pct_1s=%d.%d\n' "$((cpu_tenths/10))" "$((cpu_tenths%10))"
    else echo 'host_cpu_busy_pct_1s=unavailable'; fi
  else echo 'host_cpu_busy_pct_1s=unavailable'; fi
else
  echo 'host_cpu_busy_pct_1s=unavailable'
fi
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
cur=$(cat /sys/fs/cgroup/memory.current 2>/dev/null || :)
lim=$(cat /sys/fs/cgroup/memory.max 2>/dev/null || :)
# This is only the RAM threshold, NOT an owner/CAS/STOP/SSD/VRAM admission.
if [[ "$cur" =~ ^[0-9]+$ && "$lim" =~ ^[0-9]+$ ]]; then
  headroom=$((lim - cur))
  printf 'cgroup_mem_headroom_bytes=%s\n' "$headroom"
  if (( headroom >= 2147483648 )); then
    echo 'cgroup_ram_2gib_threshold=PASS_THRESHOLD_ONLY'
  else
    echo 'cgroup_ram_2gib_threshold=HOLD_LOW_HEADROOM'
  fi
else
  echo 'cgroup_mem_headroom_bytes=unavailable'
  echo 'cgroup_ram_2gib_threshold=HOLD_UNKNOWN'
fi
for k in cpu memory io; do
  p="/proc/pressure/$k"
  if [ -r "$p" ]; then printf 'psi_%s=' "$k"; head -n 1 "$p"; else printf 'psi_%s=unavailable\n' "$k"; fi
done
df -P -B1 / 2>/dev/null | awk 'NR==2 {printf "root_bytes_total=%s root_bytes_used=%s root_bytes_available=%s\n", $2, $3, $4}'
if [ -n "$gpu_rows" ]; then
  printf '%s\n' "$gpu_rows" | awk -F, '{printf "gpu_index=%s gpu_used_MiB=%s gpu_free_MiB=%s gpu_total_MiB=%s gpu_util_pct=%s\n", $1, $2, $3, $4, $5}'
else
  echo 'gpu_inventory=unavailable'
fi
