echo "C300: srv_k133"
df -h /workspace | tail -1
timeout 200 du -x -k --max-depth=2 /workspace 2>/dev/null | sort -rn | head -22 | awk '{printf "%.1fGB %s\n",$1/1048576,$2}'
