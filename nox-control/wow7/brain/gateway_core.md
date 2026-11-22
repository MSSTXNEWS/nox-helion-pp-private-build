# Как направить шлюз и веб в NOX CORE (флаг NOX_CORE=1, откат)

## Запуск
`python3 /root/nox/src/BRAIN/nox_core.py` (stdlib, aiohttp не нужен). Env: `NOX_CORE_PORT=8090`, `NOX_FAST_URL=http://127.0.0.1:8083`, `NOX_GLM_URL=http://127.0.0.1:8081`
(GLM напрямую, не через :8082), `NOX_CONSCIENCE=shadow` (первые сутки) -> `enforce`, `NOX_STATE`, `NOX_RECEIPTS`, `NOX_TRACE_DIR`, `NOX_BG_DEEP=1`.
Рядом должны лежать каталоги репо COMMON, RTE, PRIME, CON, EMO, MEM, ACT, MIND (пути добавляются сами); чего нет - орган просто не подключён (`GET /health` -> organs).
Проверка: `curl :8090/health`; `curl -N :8090/v1/chat/completions -d '{"messages":[{"role":"user","content":"привет"}],"stream":true}'`.

## Шлюз (glm53/gateway.py, :8082)
Одна точка: в `do_POST` при `os.environ.get("NOX_CORE")=="1"` и пути `/v1/chat/completions` - проксировать тело и заголовки как есть на `http://127.0.0.1:8090`
(потоково, байт-в-байт, включая `event: nox_phase|nox_meta`), БЕЗ собственной маршрутизации qs6/две-такта и БЕЗ добавления текста. Если CORE не отвечает (connect refused/таймаут 3 с) -
старый путь (авто-откат). `POST /v1/stop` -> на CORE `/v1/stop`. Реплика STOP-кнопки шлёт `{"turn_id": <из первого nox_meta>}`.

## Веб (web_server.py, :8080) и patch_chat.diff
1. Применить `patch_chat.diff` к `nox-control/web/patch_chat.py` (`patch -p1`), затем обычный деплой `#S1`: служебные строки больше не попадают в `content`, а идут полем `nox_phase`.
   Строка «Глубокий ответ GLM-5.3 готовлю в фоне (задача tN…)» в клоне репо не найдена - она в серверном `/root/nox/web_server.py` (или `web/*.js`); diff обезвреживает её фильтром `_clean`
   на всех путях, а при NOX_CORE=1 она не возникает вовсе.
2. С `NOX_CORE=1` веб вместо `_fb`/`_fast_text` шлёт запрос в CORE: `POST 127.0.0.1:8090/v1/chat/completions` с `nox_conversation_id` (id вкладки), `nox_turn_id` (uuid на сообщение - повтор после обрыва не плодит ходы), `nox_mode` (Авто/Быстро/Глубоко/Максимум -> auto/fast/deep/max).
3. UI: текст рисовать только из `data:`-chunk; индикатор «думаю/глубина» - из `event: nox_phase` (plan|intro|thinking|degraded|conscience|done); `nox_meta.replace` = заменить весь текст ответа; `nox_meta.stopped` - квитанция STOP;
   `nox_meta.receipt` - квитанция действия; `nox_meta.followup.url` - дочитать фоновый ответ GLM (`GET /v1/core/followup/<turn_id>`).
4. Страница «Ядро»: `GET /v1/core/trace/<turn_id>` (path, arm, model, conscience.verdict, total_ms, recall_n, executors[name,ms,status]).

## Откат
`NOX_CORE=0` (или остановить CORE) - шлюз и веб возвращаются к прежним путям с патчем `patch_chat.diff` (он безопасен и без CORE). Состояние CORE (`core_conv_*.json`, трассы, квитанции) на старый путь не влияет и просто лежит.
Мягкий режим: `NOX_CONSCIENCE=shadow` - детекторы пишут в трассу, текст не меняют.
