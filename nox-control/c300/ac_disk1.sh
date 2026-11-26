echo "C300: ac_disk1"
df -h /workspace | tail -1
find /workspace -xdev -type f -mmin -15 -size +50M -printf '%s %TT %p\n' 2>/dev/null | sort -rn | head -15
ls -la /workspace/nox/ops/dpo 2>/dev/null | head -20
du -xsh /workspace/nox/distill_v2/ckpt /workspace/nox/distill_v2/ckpt_archive /workspace/nox/distill_v2/ckpt_keep /workspace/nox/backup /workspace/nox/ops/* 2>/dev/null | sort -rh | head -8
sleep 20; df -h /workspace | tail -1
