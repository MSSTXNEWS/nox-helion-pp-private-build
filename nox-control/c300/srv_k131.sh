echo "C300: srv_k131"
df -h /workspace | tail -1; df -h / /tmp 2>/dev/null | tail -2
echo "--- deleted-but-open"; lsof +L1 2>/dev/null | awk 'NR>1 && $7>100000000{printf "%s pid=%s %.1fGB %s\n",$1,$2,$7/1e9,$10}' | head -15
echo "--- 8199"; pgrep -fa "port 8199" | cut -c1-120
echo "--- свежие большие (mmin -180)"; find /workspace /tmp /root -xdev -type f -mmin -180 -size +300M -printf "%s %TT %p\n" 2>/dev/null | sort -rn | head -12 | awk '{printf "%.1fGB %s %s\n",$1/1e9,$2,$3}'
du -sh /workspace/nox/models/student/* 2>/dev/null; du -sh /tmp /root/.cache /workspace/nox/tmp /workspace/.hf_home 2>/dev/null
