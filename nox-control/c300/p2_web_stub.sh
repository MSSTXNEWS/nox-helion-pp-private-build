#!/bin/bash
# P2: ops/draw исчез (нет в бэкапах). Временная заглушка invoke_draw (рисование отключено, чат работает), затем штатный restart веба.
echo "C300: p2_web_stub"; N=/workspace/nox; PY=$N/venv/bin/python
[ -e $N/ops/draw/invoke_draw.py ] && { echo "invoke_draw.py уже есть, ничего не делаю"; } || {
mkdir -p $N/ops/draw
cat > $N/ops/draw/invoke_draw.py <<'PYEOF'
"""ЗАГЛУШКА (P2, 2026-11-25): оригинал ops/draw/invoke_draw.py утерян (нет в бэкапах), из-за него web_server.py/chat_core.py не импортировались и :8091 лежал.
Контракт: draw_request(text)->None|(locale,prompt); photo_request(text)->bool; local_generate(prompt, cancelled=None, photographic=False)->dict(url=...).
Пока заглушка, рисование через чат выключено (draw_request всегда None, обычный чат работает). Восстановить оригинал и удалить этот файл."""
class DrawError(Exception):
    pass
def draw_request(text):
    return None
def photo_request(text):
    return False
def local_generate(prompt, cancelled=None, photographic=False):
    raise DrawError("рисование временно недоступно (заглушка invoke_draw)")
PYEOF
echo "stub created"; }
$PY -m py_compile $N/ops/draw/invoke_draw.py && echo compiled
(cd $N/web/pkg/server && $PY -c "import chat_core, brain_api; print('imports OK')" 2>&1 | tail -4)
bash $N/web/pkg/server/run_web.sh restart 2>&1 | tail -4 | cut -c1-200
for u in chat.html web/chat.html web/index.html api/chat/health; do echo "GET /$u -> $(curl -s -o /dev/null -m 8 -w '%{http_code}' http://127.0.0.1:8091/$u)"; done
echo "POST /api/chat:"; curl -s -m 60 -H 'Content-Type: application/json' -d '{"message":"Привет, ответь одним словом","messages":[{"role":"user","content":"Привет, ответь одним словом"}]}' -w '\nHTTP %{http_code} ttfb=%{time_starttransfer}s total=%{time_total}s\n' http://127.0.0.1:8091/api/chat | head -c 700
echo; tail -5 $N/agent/out/web_server.log | cut -c1-200
echo "DONE"
