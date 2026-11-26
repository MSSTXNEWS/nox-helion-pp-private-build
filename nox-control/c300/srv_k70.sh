echo "C300: srv_k70"
cd /workspace/nox
grep -n "live_turn()" integration/adapter.py | cut -c1-200
grep -n "session\|qa-" integration/adapter.py | head -30 | cut -c1-200
timeout 60 find /workspace/nox -maxdepth 3 -name "liska_restart_core*" -o -maxdepth 3 -name "restart_core*" 2>/dev/null | head
ps -eo pid,etimes,args | grep -E "adapter.py|web_server|nox_core|judge_service|pipeline|18217|nox_cascade" | grep -v grep | cut -c1-200
ls state | grep -i -E "owner|chat_hold" | head
grep -n "CHAT_HOLD *=" ops/draw/invoke_draw.py
