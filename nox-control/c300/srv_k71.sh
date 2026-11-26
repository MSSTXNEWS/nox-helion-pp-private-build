echo "C300: srv_k71"
cd /workspace/nox
W=$(readlink /proc/611127/cwd); echo $W
grep -n "chat_hold\|CHAT_HOLD\|\"qa-\|'qa-\|startswith(\"qa" $W/web_server.py | head -20 | cut -c1-220
ls -la --time-style=full-iso state/orch/chat_hold; date
grep -rn "chat_hold" --include=*.py -l . 2>/dev/null | grep -v "venv\|\.bak" | head -12
sed -n '1,40p' state/liska_restart_core.py | cut -c1-200
