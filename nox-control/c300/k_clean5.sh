#!/bin/bash
# Owner 25.11 18:00 MSK: "удали использованное обучение - автоочистка - старт"
echo K_CLEAN5
df -h /workspace | tail -1
RUN=$(ps -eo args | grep -E 'distill|train|autotrain|v5_' | grep -v grep)
for d in /workspace/nox/ops/v5_catalog_101_20261125 /workspace/nox/ops/v5_catalog_context50_20261125 /workspace/nox/distill_v2/ready_pool_gb10 /workspace/nox/ops/causal_conv1d_probe_20261125 /workspace/nox/distill_v2/archive_pre_fix_20261123; do
  [ -e "$d" ] || continue
  if echo "$RUN" | grep -q "$(basename $d)"; then echo "SKIP in-use $d"; continue; fi
  if find "$d" -mmin -120 | head -1 | grep -q .; then echo "SKIP recent $d"; continue; fi
  echo "DEL $(du -sh $d | cut -f1) $d"; rm -rf "$d"
done
cat > /workspace/nox/disk_janitor.sh <<'J'
#!/bin/bash
# Owner-approved auto-cleanup: archived/rejected checkpoints and package caches, hourly
while true; do
  rm -rf /workspace/nox/distill_v2/ckpt_archive/* /workspace/nox/distill_v2/ckpt_keep/rejected_* /root/.npm/_cacache /root/.cache/pip 2>/dev/null
  echo "$(date -u +%FT%TZ) $(df -h /workspace | tail -1)" >> /workspace/nox/disk_janitor.log
  sleep 3600
done
J
chmod +x /workspace/nox/disk_janitor.sh
pgrep -f disk_janitor.sh >/dev/null || (nohup /workspace/nox/disk_janitor.sh >/dev/null 2>&1 &)
pgrep -f disk_janitor.sh >/dev/null && echo JANITOR_ON
echo AFTER; df -h /workspace | tail -1
