#!/bin/bash
# L1 disk_report: READ-ONLY. Top-20 heavy paths + cleanup candidates. Deletes nothing.
# usage: disk_report.sh [ROOT_DIR ...]   (default: /root/nox /var/log /tmp /root/.cache)
set -u
ROOTS=("$@"); [ ${#ROOTS[@]} -eq 0 ] && ROOTS=(/root/nox /var/log /tmp /root/.cache)
echo "== df"; df -h / 2>/dev/null | tail -n +1
echo "== top-20 heaviest paths (depth<=3)"
for r in "${ROOTS[@]}"; do [ -d "$r" ] && du -x -d 3 -k "$r" 2>/dev/null; done | sort -rn | head -20 \
  | awk '{printf "%8.1f GiB  %s\n",$1/1048576,$2}'
echo "== cleanup CANDIDATES (nothing is deleted; review manually)"
for r in "${ROOTS[@]}"; do [ -d "$r" ] || continue
  echo "-- old/rotated logs >50MiB in $r"; find "$r" -xdev -type f \( -name '*.log' -o -name '*.log.*' -o -name '*.gz' \) -size +50M 2>/dev/null | head -10
  echo "-- *.bak* / *.tmp / *.old >100MiB in $r"; find "$r" -xdev -type f \( -name '*.bak*' -o -name '*.tmp' -o -name '*.old' \) -size +100M 2>/dev/null | head -10
  echo "-- checkpoints dirs (older than 7d, >1GiB)"; find "$r" -xdev -type d \( -name 'checkpoint-*' -o -name 'ckpt*' \) -mtime +7 2>/dev/null | head -10 | while read -r d; do du -sk "$d" 2>/dev/null | awk '$1>1048576{printf "%.1f GiB %s\n",$1/1048576,$2}'; done
  echo "-- *.gguf >5GiB (models: owner decides, do not remove)"; find "$r" -xdev -type f -name '*.gguf' -size +5G 2>/dev/null | head -10
done
for c in /root/.cache/huggingface /root/.cache/pip /var/cache/apt /var/lib/apt/lists; do [ -d "$c" ] && du -sh "$c" 2>/dev/null; done
echo "== end (read-only)"
