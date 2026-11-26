echo "C300: srv_k134"
cd /workspace/nox/memory; ls -la --time-style=+%F_%T . | head -20
find . -type f -size +500M -printf "%s %TT %p\n" | sort -rn | head -8 | awk '{printf "%.1fGB %s %s\n",$1/1e9,$2,$3}'
du -k --max-depth=2 . | sort -rn | head -8 | awk '{printf "%.1fGB %s\n",$1/1048576,$2}'
pgrep -fa "memory" | grep -v pgrep | cut -c1-140 | head -5; df -h /workspace|tail -1
