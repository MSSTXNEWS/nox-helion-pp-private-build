cd /workspace/nox/web/pkg/server
ls; grep -n "уже идёт ответ\|inflight\|_turns\|running\|turn_id\|/api/turn" web_server.py | cut -c1-210 | head -60
