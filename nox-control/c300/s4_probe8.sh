N=/workspace/nox
echo "S4P8 $(date +%F_%H:%M)"
PID=$(ss -ltnp 2>/dev/null | grep ':18220 ' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); echo "pid=$PID"
CMD=$(tr '\0' ' ' < /proc/$PID/cmdline 2>/dev/null); echo "cmd=$CMD"
F=$(echo "$CMD" | tr ' ' '\n' | grep '\.py$' | head -1); case "$F" in /*) ;; *) F=$(readlink /proc/$PID/cwd)/$F;; esac; echo "file=$F size=$(stat -c %s $F)"
grep -n -i -E "user|incognito|@app|route|def (recall|add_fact|remember|list|post|handle)|path ==|startswith\(\"/" $F | cut -c1-230 | head -90
