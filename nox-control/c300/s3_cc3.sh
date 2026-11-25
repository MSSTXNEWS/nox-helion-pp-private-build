F=/workspace/nox/web/pkg/server/chat_core.py
echo "== CC3"; sed -n 282,305p $F | cut -c1-240; sed -n 316,322p $F | cut -c1-240
grep -n "/api/chat\"\|/api/chat'\|api/chat/send\|def do_POST" /workspace/nox/web/pkg/server/web_server.py | head -6 | cut -c1-200
