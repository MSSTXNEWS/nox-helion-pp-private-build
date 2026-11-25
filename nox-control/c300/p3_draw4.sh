N=/workspace/nox
P=$(pgrep -f "python web_server.py"|head -1); echo "web pid $P ppid=$(ps -o ppid= -p $P) cwd=$(readlink /proc/$P/cwd) age=$(ps -o etimes= -p $P)"; tr '\0' '\n' </proc/$P/environ | grep -E "^NOX_|^PYTHONPATH" | sed -E 's/(KEY|TOKEN|SECRET)=.*/\1=***/' | head -12
echo "== launch/restart refs"; grep -rIl --exclude-dir=backup --exclude-dir=venv --exclude-dir=node_modules -E "web_server\.py" $N/ops $N/serve $N/agent/out/*.sh $N/*.sh /.launch 2>/dev/null | head -8
grep -n "web_server" /.launch 2>/dev/null | head -5 | cut -c1-200
echo "== liska_restart_core.py"; sed -n 1,25p $N/state/liska_restart_core.py | cut -c1-180
echo "== supervisor program for web?"; supervisorctl status 2>/dev/null | head -15
echo "== owner silence"; cat $N/state/orch/chat_hold; ls -la --time-style=+%T $N/state/orch/chat_hold
echo "== web threading?"; grep -n -E "ThreadingHTTPServer|HTTPServer\(|serve_forever" $N/web/pkg/server/web_server.py | head -3
