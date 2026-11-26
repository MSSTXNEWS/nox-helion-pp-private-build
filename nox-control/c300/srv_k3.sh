echo "C300: srv_k3"
P=$(ss -ltnp | grep ":8810 " | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); echo pid $P
tr '\0' ' ' </proc/$P/cmdline; echo; readlink /proc/$P/cwd
D=$(readlink /proc/$P/cwd)
grep -rIln "worms" $D --include=*.py 2>/dev/null | head
ss -ltnp | grep ":8143 "; ps aux | grep -E "8143" | grep -v grep | head -2
