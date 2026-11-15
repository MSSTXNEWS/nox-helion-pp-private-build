# NOX HELION — ЕДИНЫЙ СПРАВОЧНИК ВСЕХ СПОСОБОВ ПОДКЛЮЧЕНИЯ К ONEHOST

**Дата фиксации:** 2026-11-15 · **instructions_version:** 0.0.6 · **Аудитория:** MANUAL №1/№2, AUTO 1A→2A→1B→2B→1C→2C, последующие агенты, владелец.  
**Объект:** ОДИН исходный NOX на Vast.ai instance **#60509551**. Приватный исходный репозиторий `MSSTXNEWS/nox-helion-pp-private-build`; координация [PR #256](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/pull/256).  
**Назначение:** не искать заново работающий способ, не путать авторизацию Vast, SSH, HTTP и работоспособность модели. Все нижеописанные пути разной зрелости: не выдавать SOURCE или TCP за LIVE.

## Быстрая таблица — что реально работает

| № | Канал | Проверенное состояние на 15.11.2026 | Для чего |
|---|---|---|---|
| 1 | Официальный Vast API **v1** + GitHub Actions `NOX2` | **OWNER AUTH VERIFIED**, HTTP 200, исходный instance найден | Проверить instance и получить актуальную SSH mapping |
| 2 | Изолированный GitHub runner + **V51 pinned ED25519 ephemeral SSH** | **NATIVE READ-ONLY PASS**, ключ удалён | Диагностика существующих GPU, памяти, диска, процессов, OneHost |
| 3 | Owner HTTP через работающий `:8080`/нутренний `:8081` после SSH | **NATIVE ROUTES/HEALTH/S03 TABLES VERIFIED**; модельный E2E V124/V125 исторически PASS | Открыть исходный WEB, проверить chat/S03; новый `pc/resonance.html` E2E ещё не принят |
| 4 | Постоянный SSH-ключ в `NOX_VAST_SSH_PRIVATE_KEY` | **NOT CONFIGURED** по физической проверке | Запасной прямой вход при управляемом ключе и pinned host |
| 5 | Прямые/прокси SSH порты Vast | **TCP+SSH BANNER PASS, NOT AUTH** без ключа | Только первичная диагностика; самостоятельно не открывает OneHost |
| 6 | WEB владельца по cookie (`/chat/login`, `/chat/session`) | **Исторический native PASS** | Авторизованный доступ к оригинальному чату с того же OneHost |
| 7 | Подписанный V49 GitHub inbox→OneHost HMAC bridge | **SOURCE ONLY / живых receipts нет** | Потенциальный командный канал, если агент реально установлен и использует отдельный owner signer |
| 8 | `nox-control` / `NOX_MASTER.json` / 180-секундный poller | **SOURCE, no verified live writeback** | Считывание allowlisted read-only заданий, НЕ универсальный терминал |
| 9 | Локальный Windows `127.0.0.1` и WebView2/OneHost | **Исторические локальные пути, текущий remote доступ не доказан** | Только на самом Windows PC, не из облака ChatGPT |
| 10 | Сохранённая браузерная сессия Vast / TinyFish | **NO SIGNED-IN PROFILE**, браузерный доступ недоступен в проверке | Резерв только после добровольного owner login |
| 11 | Vercel NOX WEB preview | **READY PREVIEW, NOT native model** | Смотреть фронтенд, не считать подлинным чатом |
| 12 | Google Drive / Tigris / R2 / RunPod | **Storage / другие сервисы, NOT Vast owner authorization** | Холодное хранение/артефакты; не заменяют доступ к OneHost |

## 1. Основной рабочий способ: Vast API v1 с имеющимся ключом NOX2

**Первым делом** выполнить авторизованный **GET** к одному из проверенных адресов:
- `https://cloud.vast.ai/api/v1/instances`
- `https://console.vast.ai/api/v1/instances`

**Источники полномочий:** GitHub Actions repository secret `NOX2` (дополнительно в отдельном V173 был подтверждён именованный secret `NOX`). Только GitHub runner `env:` / переменная процесса; никогда не включать значение ключа в код, лог, PR, Notion, веб-страницу или shell history.

Минимальный корректный алгоритм:
1. HTTP заголовок `Authorization: Bearer <значение из GitHub Secret>`, `Accept: application/json`; метод **GET**.
2. Требовать `HTTP 200` и структурированный ответ JSON.
3. Из списка `instances` выбрать **строго `id == 60509551`**. Не считать 200 без точного id авторизацией к нужному серверу.
4. До нативных операций дополнительно проверить `actual_status == "running"`, число GPU, текущую карту портов и публичный IP в возвращённой записи, не публикуя полный приватный объект.
5. Если `404/410` на **`/api/v0/instances/`** — это УСТАРЕВШИЙ МАРШРУТ, **не** основание менять NOX2, объявлять инстанс удалённым или переустанавливать NOX. Сначала перейти на v1.
6. Если v1 не проходит, разделять HTTP, error-класс, наличие секрета и отсутствие искомого instance; не подбирать ключи и не обходить owner ACL.

**Доказательство:** [Vast v1 HTTP 200, target found #43721473311](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43721473311), а также [V173 #43721717744](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43721717744). Файл [рабочей API-диагностики](../.github/workflows/nox-existing-onehost-origin-readonly.yml) использует ограниченный вывод. Ранние `auth_error` 404 из v0 — исторически **ошибочная диагностика**, а не доказанная порча секрета.

## 2. Основной нативный способ: owner-pinned временный SSH V51 (API v1 → SSH → cleanup)

После успешного пункта 1 используем **один уже существующий** V51:
- [Python native probe](../nox_runpod/teacher_mesh/v51/ephemeral_ssh_probe.py);
- [рабочий v1 SSH audit workflow](../.github/workflows/nox-original-onehost-v1-native-readonly.yml);
- [физический native PASS #43721724993](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43721724993);
- [физический WEB/S03 read-only #43721938273](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43721938273).

**Порядок — без пропусков:**
1. Получить реальную запись `id=60509551` через рабочий owner API v1, убедиться, что `running`.
2. Найти актуальные `public_ipaddr` и `ports["22/tcp"]` **из той же авторизованной записи**. Исторический `ssh9.vast.ai:26623` / `166.113.48.41:11234` не является вечной конфигурацией; маршрут может измениться.
3. Прежде чем прикасаться к SSH-ключам экземпляра: получить SSH-2.0 banner и **сверить ED25519 host fingerprint** с закреплённым владельцем `SHA256:G4hmMllaT4uSfx+Gup9vjSySLXJT1cSc/9XePr7XmGc`. При расхождении HOLD, **НЕ** отключать `StrictHostKeyChecking`.
4. Только в изолированном краткоживущем GitHub runner с owner-scoped секретом сгенерировать временный `ed25519` keypair; **приватный ключ остаётся в runner**, на Vast через официальный per-instance endpoint добавляется только временный публичный ключ. Метод instance SSH key attach в действующем V51 отдельный от снятого с обслуживания v0 **list instances**.
5. Записать локальный cleanup-tracker **до** попытки attach, проверять конкретный `key_id` посредством exact публичного ключа; не вмешиваться в чужие ключи.
6. Подключиться `ssh -T` с `BatchMode=yes`, `IdentitiesOnly=yes`, `StrictHostKeyChecking=yes` и pinned `known_hosts`. При transient `Permission denied` / timeout применять только ограниченные retry оригинального V51.
7. Выполнять только заранее проверенную **READ-ONLY** нативную диагностику оригинальных сервисов. Не перезапускать модель, сервер, тренер, менять веса или S03 ради проверки.
8. **Всегда в `finally` и `if: always()`:** удалить только собственный temporary public key по id и **повторным запросом убедиться в отсутствии**. При отсутствии подтверждения удаления статус `HOLD_CLEANUP` даже если SSH-команда была успешной.
9. Разделять `API_AUTH_PASS`, `SSH_AUTH_PASS`, `REMOTE_COMMAND_PASS`, `TEMP_KEY_REMOVED_VERIFIED` и `LIVE_WEB_PASS` — это НЕ синонимы.

**Результат 15.11:** реальные native GPU/Python/память/диск были прочитаны; временный ключ удалён и сверено `TEMP_SSH_CLEANUP=DETACHED_AND_VERIFIED`. Некоторые попытки SSH сначала получали `Permission denied`/timeout, затем установлен успешный read-only канал. Не объявлять попытку №1 провалом всего метода.

## 3. Подключение именно существующего WEB, «Резонанса» и S03 по owner HTTP

**Точка доступа после SSH внутри OneHost:** `http://127.0.0.1:8080` (основной оригинальный owner proxy), `http://127.0.0.1:8081` (смежный исходный сервис, `/health` и `/slots`). **Эти loopback-адреса не открываются с удалённого ПК напрямую**. Не публиковать их наружу и не делать новый HTTP backend.

**Проверенные файлы и URL:**
- исходный `/root/nox/scripts/chat_proxy.py`;
- исходный `/root/nox/scripts/nox_v29_chat_bridge.py`;
- исходный WEB `/root/nox/incoming_t800u/v29_3/NOX_HELION_WEB_V29_3_FROZEN_20261113/site`;
- `GET /nox-web-v29/chat.html` и **`GET /nox-web-v29/pc/resonance.html`**;
- `POST /api/nox/chat/stream`, `POST /api/ui/memory/dialogs/create`, `GET /api/ui/memory/dialogs/history`, `GET /api/nox/status`;
- `GET /nox-web-v29/native-owner.js` — **синтетический owner script, выдаётся `_OwnerStatic`**; физическое отсутствие файла на диске НЕ является HTTP-отсутствием.

**Проверено физически на OneHost #43721938273:** `:8080/health=200`, `:8081/health=200`, обе оригинальные HTML страницы существуют; анонимный запрос к owner страницам и owner script возвращает HTTP **401**; указанные 4 native API маршрута зарегистрированы; базовые SQLite S03 таблицы есть; 6 model slots были idle во время конкретной проверки. Это **не** доказательство отсутствия влияющих параллельных процессов в любое другое время.

**Отдельное текущее несоответствие:** в проверенном статическом каталоге нет физического `nox-v135-resonance-owner-bridge.js`. Но наличие/необходимость загрузки этого файла в *живой* HTML надо проверять через авторизованный HTTP-ответ и сетевой браузерный trace, а не угадывать по файловому пути. Не копировать V135 в production автоматически и не менять работающий чат без подтверждённого 404/JS error/route mismatch. `native-owner.js` статически **не обязан** существовать.

**Вход владельца:** существующий owner-only `POST /chat/login` → HttpOnly cookie → `GET /chat/session`. Пароль разрешено получать только уже существующей серверной функцией `chat_proxy._read_chat_password()` в исходном localhost owner runtime; ни пароль, ни cookie/заголовки не печатать и не передавать. После проверки logout/закрыть сессию.

**Одна полноценная приёмка «Резонанса»:**
1. В owner-authorized браузере `GET /nox-web-v29/pc/resonance.html` → 200; убедиться в загруженных исходных скриптах (HTTP и console/network, не только наличие HTML).
2. Отправить ограниченный контрольный запрос через уже существующий `POST /api/nox/chat/stream` — никакой подставной модели или mocked JS. Зафиксировать настоящий first delta, последовательность кадров, полное окончание, измеренные TTFT и total latency.
3. Принять `done.saved=true` + `s03_integrated=true` + native `exchange_id` **только после** `GET /api/ui/memory/dialogs/history` и совпадающего реального ответа в исходной S03. Ошибка/STOP/incomplete → HOLD.
4. Проверить RU и ES, полные ответы и отсутствие раскрытия чужих owner/persona диалогов. Не копировать приватный диалог в CI; публиковать только результат, время и SHA/receipt.
5. Только при обнаруженном live дефекте делать **один минимальный обратимый** патч поверх существующего OneHost с точным preimage SHA, backup+rollback и повторной физической E2E; нельзя создавать второй frontend/backend/model.

**История успехов:** owner login + original `/nox-web-v29/chat.html` + real model stream + native S03 в [V114 #43643685473](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43643685473), [V124 #43648080575](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43648080575), [V125 #43650605385](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43650605385). **Новая физическая E2E именно `pc/resonance.html` всё ещё требует проверки**, старые PASS нельзя механически переносить.

## 4. Резервный SSH с постоянным ключом (не настроен)

[Проверенный GitHub Actions pinned SSH source](../.github/workflows/nox-existing-onehost-pinned-ssh-readonly.yml), [реальный запуск #43720087615](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43720087615).

- Опциональные секреты: `NOX_VAST_SSH_PRIVATE_KEY` и `NOX_VAST_SSH_KNOWN_HOSTS` в GitHub Secrets. Результат реального runner: `HOLD_MISSING_SECRET`; **не считать метод сейчас готовым**.
- Если владелец когда-либо настроит *уже разрешённый* приватный ключ, проверять его формат локально в runner, никогда не печатать содержимое; требуется точное совпадение серверного host-key pin и исходного target.
- Использовать строго read-only и `BatchMode=yes`; не пробовать чужие учётные данные, `StrictHostKeyChecking=no` или обход ACL.
- Наличие открытого TCP/SSH-баннера **не** является доступом. Рабочий V51-ephemeral метод предпочтительнее.

## 5. GitHub→OneHost HMAC bridge V49 и старый GitHub master poller

**V49:**
- [Исходный код](../nox_runpod/teacher_mesh/v49/onehost_bridge.py).
- [Inbox](bridge/NOX_BRIDGE_INBOX.json) и [Receipts](bridge/NOX_BRIDGE_RECEIPTS.json): при проверке были `requests=[]`, `receipts=[]`, `live_bridge_verified=false`.
- Если уже установленный owner агент в исходном OneHost реально опрашивает inbox, команда допускается только с **owner-side HMAC signer и надёжным подписанным receipt**. Общеизвестный текст в GitHub или комментарий PR не является подписанной командой.
- Не создавать HMAC-фальшивки, не просить ChatGPT «выполнить через мастер файл», если native подписанное исполнение не доказано. Здесь SOURCE, НЕ live access.

**`nox-control`:**
- [`NOX_MASTER.json`](../nox-control/NOX_MASTER.json), [`nox_agent.py`](../nox-control/nox_agent.py), [README](../nox-control/README.md). Список разрешённых действий исторически: `health`, `gpu_status`, `nox_status`. Poll `180` секунд.
- Этот agent пишет результат **локально** в `~/.nox-control/completed.json`; в его README нет подтверждённого remote writeback. Старые manifest targets `windows/runpod-a40/runpod-a5000/contabo` — не замена актуальной Vast #60509551 и не автоматическое доказательство работающего bridge.
- Не выполнять произвольный shell, обновления весов, очистку SSD или GPU STOP посредством public master; это иной trust-boundary.

## 6. Windows / localhost / Vercel / браузер / Drive — что они могут и чего не могут

- **Windows owner PC**: исторические localhost `127.0.0.1:18775`, `127.0.0.1:18877`, отдельные WPF/WebView2/NOX service пути. Это адреса **только самого ПК**. У ассистента нет подтверждённого текущего удалённого доступа к Windows, а доступ к Vast не означает доступ к ПК. Проверять local PID, owner auth и mounted SHA перед изменением.
- **Vercel preview**: `nox-helion-real-home-preview` и другие проекты в Vercel READY означают возможность просмотра собранного UI; это НЕ authenticated OneHost / S03 / реальный ответ NOX. Не считать image/demo/previews native live.
- **Vast веб-консоль через браузер**: только после реального входа владельца в собственном профиле; прошлый TinyFish профиль `Vast.ai — NOX isolated` не имел подтверждённого `signed_in_sites`, кошелёк был недостаточен. Не подменять учетку чужими cookies.
- **Google Drive / Tigris / R2**: хранят пакеты, веса/резервные копии, не дают права на Vast SSH. Tigris `nox2` — **S3 credential другого провайдера**, не `NOX2` Vast API. Скачивать модели/чистить диски лишь после SHA + проверенного offsite restore и native resource lease.
- **Другие облачные GPU** (RunPod и т.п.) не дают доступа к тому же оригинальному OneHost. Не создавать новую платную VM или вторую модель для «починки» исходного WEB.

## 7. Как НЕ повторить ошибку: симптомы → правильное решение

| Симптом | Верный вывод / действие |
|---|---|
| `/api/v0/instances/` → HTTP 404/410 | Устаревший account API; проверить **v1** прежде чем просить сменить ключ |
| v1 → HTTP 200, нет точного `60509551` | Авторизация какой-то области есть, нужный экземпляр НЕ доказан |
| v1 HTTP 200, `id=60509551`, `running` | Только **VAST API AUTH PASS**; ещё не SSH, WEB или модель |
| SSH TCP/баннер OK | Порт отвечает, но нет owner authorization |
| SSH попытки №1–№3 Permission denied/timeout | Не делать ложный FAIL, если bounded retry №4 + private exact proof PASS; cleanup обязательно |
| Host fingerprint не совпадает | STOP/HOLD, никаких key attach |
| TEMP SSH удаление не подтверждено | HOLD_CLEANUP, не PASS |
| `native-owner.js` отсутствует на диске | Может быть **динамическим** из защищённого `_OwnerStatic`; проверить HTTP |
| V135 bridge.js отсутствует на диске | Проверить настоящий owner HTML/network, не переписывать WEB наугад |
| Source CI зелёный | Только SOURCE VERIFIED, не native deploy |
| S03 таблицы существуют | Только schema ready, не доказательство commit/history для конкретного ответа |
| GPU 1 занят / свободно ~16.5 GB SSD | Нельзя запускать второй trainer, огромную загрузку/очистку без lease/backup/restore |
| NOX отвечает на V114 `chat.html`, а `pc/resonance.html` не проверяли | Сохранить исторический PASS в своём scope; отдельная browser acceptance по целевой странице |

## 8. Единый handoff/приёмка для всех исполнителей

1. Получить **актуальный HEAD** PR #256 + последний append-only receipt, сверить с [мастером](NOX_PRIME_SIX_RELAY_20261115.md) и [канонической памятью Notion](https://app.notion.com/p/40cacc184a9f81248703e3840d4c2422).
2. **Сначала** применить метод №1 и №2 (не повторять deprecated v0). Не печатать секреты/сессии.
3. Снять единую **native read-only** квитанцию с URL исходного origin, source SHA, owner HTTP status, REGISTERED endpoints, S03 readiness, STOP, active workers; затем если authorized — один bounded genuine E2E «Резонанс».
4. Статус по независимым границам: `VAST_OWNER_AUTH`, `SSH_REMOTE_READ`, `TEMP_KEY_REMOVED`, `OWNER_WEB_LOGIN`, `RESONANCE_HTML_JS_LOADED`, `MODEL_FIRST_DELTA`, `MODEL_FULL_DONE`, `S03_DURABLE_READBACK`, `BROWSER_RU_ES_E2E`. Для финального WEB PASS нужны все соответствующие реальные доказательства.
5. Любая операция на весах, S03, модельной очереди, диске, GPU требует отдельного owner-native допуска, сохранённого preimage SHA и безопасного rollback. **Этот справочник не даёт разрешения изменять production.**
6. Один патч → одна итоговая комплексная проверка → одно сохранение. Никаких fake PASS, новых backend/VM или force-push. При конкурентном writer перечитать HEAD и ожидать/передать, не затирать чей-то результат.

**Долговечность:** полный текст и исходники — в GitHub, ключевые факты и ссылка — в канонической NOX Memory/Notion. Сохранённые ссылки/хэши отражают конкретные моменты времени: перед следующим подключением сверять актуальный instance, hostname, port, HEAD и owner permission.
