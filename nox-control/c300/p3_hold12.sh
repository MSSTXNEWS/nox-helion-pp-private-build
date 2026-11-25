N=/workspace/nox; F=$N/stewards/nox_orch.py; cp -p $F $F.bak_p3c_$(date +%H%M%S)
python3 - "$F" <<'PY'
import sys
p=sys.argv[1]; s=open(p).read()
if "|^k\\d+$|" in s: print("already")
else:
    s=s.replace("|^qa[-_]","|^qa[-_]|^k\\d+$|",1); open(p,"w").write(s); print("patched k\\d+")
PY
$N/venv/bin/python -m py_compile $F && echo syntax ok
G=$(cat $N/state/orch/guard.pid); CMD=$(tr '\0' ' ' </proc/$G/cmdline); CWD=$(readlink /proc/$G/cwd); kill -TERM $G; sleep 4
if ! pgrep -f "stewards/chat_guard.py" >/dev/null; then cd $CWD; setsid nohup $CMD >> $N/state/orch/guard.stdout 2>&1 < /dev/null 9>&- & disown; sleep 3; fi
echo "guard: $(pgrep -f stewards/chat_guard.py | head -1)"
