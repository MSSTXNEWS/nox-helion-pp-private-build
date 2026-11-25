#!/bin/bash
echo K_CLEAN4
df -h /workspace | tail -1
du -sh /workspace/nox/distill_v2/ckpt_archive /workspace/nox/distill_v2/ckpt_keep/rejected_* /root/.npm/_cacache /root/.cache/pip 2>/dev/null
rm -rf /workspace/nox/distill_v2/ckpt_archive/* /workspace/nox/distill_v2/ckpt_keep/rejected_* /root/.npm/_cacache /root/.cache/pip
echo AFTER
df -h /workspace | tail -1
du -sh /workspace/nox/distill_v2 /workspace/nox/ops 2>/dev/null
