P=/workspace/nox/web/pkg/server
echo "== CC5"; grep -n "нет сообщения пользователя" -B8 $P/web_server.py | cut -c1-220 | head -24
grep -n "confirm" $P/nox_cmd.py | cut -c1-230 | head -20
