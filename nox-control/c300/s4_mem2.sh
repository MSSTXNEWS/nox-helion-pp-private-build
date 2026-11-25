echo S4RUN:s4_mem2
ss -ltnp 2>/dev/null | grep ":8095" | head -2
PID=$(ss -ltnp 2>/dev/null | grep ":8095" | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); echo PID=$PID; tr '\0' ' ' < /proc/$PID/cmdline; echo; ls -l /proc/$PID/cwd
grep -n "MEM_PATHS\|^MEM *=" /workspace/nox/web/pkg/server/web_server.py | head -4
D=$(readlink /proc/$PID/cwd); for f in $(tr '\0' '\n' < /proc/$PID/cmdline | grep '\.py$'); do F=$f; case $f in /*) ;; *) F=$D/$f;; esac; echo FILE=$F; wc -l $F; grep -n "empty text" -B25 $F | cut -c1-200 | head -70; done
