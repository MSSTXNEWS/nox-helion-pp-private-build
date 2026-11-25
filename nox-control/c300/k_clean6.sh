#!/bin/bash
# Owner 25.11 19:03 MSK: "удали все старое и лишнее" — remove finished/old training artifacts not in use
echo K_CLEAN6
df -h /workspace | tail -1
RUN=$(ps -eo args | grep -E 'distill|train|autotrain|v5_|llama|python' | grep -v grep)
for d in /workspace/nox/ops/v5_* /workspace/nox/ops/draw /workspace/nox/distill_v2/pool_*_pending /workspace/nox/distill_v2/tcache; do
  [ -e "$d" ] || continue
  b=$(basename "$d")
  if echo "$RUN" | grep -q "$b"; then echo "KEEP in-use $b"; continue; fi
  if find "$d" -mmin -180 2>/dev/null | head -1 | grep -q .; then echo "KEEP recent $b"; continue; fi
  echo "DEL $(du -sh "$d" | cut -f1) $b"; rm -rf "$d"
done
# adapters: keep 2 newest gguf
cd /workspace/nox/ops/v5_live_adapter_20261125 2>/dev/null && ls -1t *.gguf 2>/dev/null | tail -n +3 | while read f; do echo "DEL adapter $f"; rm -f "$f"; done
# backups: keep newest 2 of each prefix
cd /workspace/nox/backup 2>/dev/null && for p in $(ls -1 | sed -E 's/_[0-9]{8}.*//' | sort -u); do ls -1td ${p}_2* 2>/dev/null | tail -n +3 | while read f; do echo "DEL backup $f"; rm -rf "$f"; done; done
echo AFTER; df -h /workspace | tail -1
