echo "C300: srv_k132"
df -h /workspace | tail -1
find /workspace -xdev -type f -mmin -90 -size +500M -printf "%s %TT %p\n" 2>/dev/null | sort -rn | head -12 | awk '{printf "%.1fGB %s %s\n",$1/1e9,$2,$3}'
find /workspace/nox/models -xdev -maxdepth 3 -type d -mmin -90 2>/dev/null | head
pgrep -fa "huggingface|hf_hub|snapshot_download|hf download|wget|curl" | grep -v pgrep | cut -c1-160 | head -5
du -sh /workspace/nox/models/* 2>/dev/null | sort -rh | head -6
