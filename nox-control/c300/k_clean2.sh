#!/bin/bash
echo K_CLEAN2
df -h /workspace | tail -1
du -sh /root/.npm/_cacache /root/.cache/pip /workspace/nox/web/build/node_modules /workspace/nox/distill_v2/ckpt_archive /workspace/nox/distill_v2/ckpt_keep/rejected_* /workspace/nox/ops/v5_live_adapter_20261125/r024-* 2>/dev/null
rm -rf /root/.npm/_cacache /root/.cache/pip
rm -rf /workspace/nox/web/build/node_modules
rm -rf /workspace/nox/distill_v2/ckpt_archive/*
rm -rf /workspace/nox/distill_v2/ckpt_keep/rejected_*
rm -rf /workspace/nox/ops/v5_live_adapter_20261125/r024-*
cd /workspace/nox/backup 2>/dev/null && for p in $(ls -1 | sed -E 's/_[0-9]{8}_[0-9]{6}.*//' | sort -u); do ls -1td ${p}_2* 2>/dev/null | tail -n +3 | xargs -r rm -rf; done
echo AFTER
df -h /workspace | tail -1
