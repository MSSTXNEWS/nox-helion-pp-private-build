N=/workspace/nox
df -h /workspace | tail -1
du -xsh $N/backup/* 2>/dev/null | sort -rh | head -8
du -xsh $N/distill_v2/ckpt $N/distill_v2/ckpt_keep $N/distill_v2/ckpt_archive $N/distill_v2/checkpoint_evidence 2>/dev/null
ls -la $N/distill_v2/ckpt_archive | head -12 | cut -c30-140
du -xsh /root/.cache /tmp $N/hf_home $N/state/advisor_images $N/agent/out $N/tmp 2>/dev/null
find $N -xdev -type f -size +1G -mmin -300 -not -path "*/models/*" 2>/dev/null | xargs -r ls -la | awk '{print $5,$9}' | head -8
