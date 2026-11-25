# ADVISORS_EXT: внешние советники NOX (исполнитель V)
Бесплатные открытые модели через единый локальный шлюз. Только официальные бесплатные пути (Kilo free-модели анонимно, LLM7 анонимный тариф, AI Horde, Pollinations classic, бесплатные тарифы провайдеров с ключом). Никаких обёрток веб-чатов (gpt4free, duck.ai и т.п.).

## Связь с существующей системой
Уже работали: шлюз-лимитчик :4210 (keyless_shim: kilo, llm7, horde, pollinations), LiteLLM :4000 (29 алиасов advisor-*), маршрутизатор :4220, шлюз приватности :4100. Новый шлюз :8793 не дублирует их, а даёт единый OpenAI-вход `провайдер/модель` поверх :4210 (общие лимиты и кулдауны сохраняются), добавляет свою фильтрацию, кэш, квоты и реестр. Консилиум/субисполнители могут звать :8793 напрямую либо по-прежнему :4220.

## Шлюз
- Код: /workspace/nox/advisors/gateway.py (stdlib, без зависимостей). Лог: /workspace/nox/svc/logs/advisors.log. Порт 127.0.0.1:8793, в svc_registry.json ключ `advisors_gw`, автозапуск в /workspace/nox/svc/start_extra.sh.
- `POST /v1/chat/completions` (OpenAI-формат). `model` = `провайдер/модель` (например `llm7/gpt-oss-20b`), либо `auto` (цепочка по реестру, фолбэк на следующего), либо `провайдер/auto`.
- `GET /v1/models` список с полями available, needs_key, key_set, status, latency_ms, плюс usage (квоты за день). `GET /health`.
- В ответе поле `nox`: provider, redacted (сколько фрагментов вырезано), ms, tried (неудачные попытки), cached.
- Ретраи (cfg.retries), таймаут (cfg.timeout), кэш (cfg.cache_ttl, в памяти), лимит частоты на провайдера (интервал + RPM), дневной счётчик /workspace/nox/state/advisors_usage.json, карантин упавшей модели (60 с при 429/402, 10 мин при 401/403/404).

## Реестр советников
/workspace/nox/state/advisors_external.json: {updated, gateway, advisors:[{id, provider, model, strengths, status ok|weak|fail|need_key|untested, latency_ms, needs_key, key_env, limits, sample}]}. Пересборка: `python3 /workspace/nox/advisors/register.py` (шлюз должен работать). Консилиум и субисполнители берут `status in (ok)` и зовут шлюз с `model=<provider>/<model>`; для голосования волнами достаточно списка id.

## Ключи (когда владелец даст)
Вписать значение в /workspace/nox/state/secrets/advisors.env (chmod 600), шлюз читает файл на каждом запросе, перезапуск не нужен. Затем запустить register.py.
OPENROUTER_API_KEY (модели :free), GITHUB_MODELS_TOKEN (PAT с правом models:read), GROQ_API_KEY, CEREBRAS_API_KEY, GEMINI_API_KEY (Google AI Studio), MISTRAL_API_KEY, LLM7_API_KEY (необязательно, 120 RPM), POLLINATIONS_API_KEY (необязательно).

## Приватность
/workspace/nox/state/advisors_cfg.json: `external_enabled` (true/false, выключатель «можно наружу»), `allow_personal` (false по умолчанию), `personal_terms` (слова/имена владельца для вырезания), `auto_chain`, `max_tokens_cap`. Перед отправкой из всех сообщений вырезаются: ключи и токены (sk-, ghp_, github_pat_, hf_, AIza, Bearer, key=value, private key), пути (/workspace, /home, ...), email, IP, длинные hex/base64. Пока allow_personal=false также: телефоны, паспортные номера, адрес/суд по делу владельца и personal_terms. Ключи и секреты NOX в запросы не попадают; ответы шлюза не содержат ключей.

## Ограничения
Анонимные тарифы без SLA, лимиты могут меняться. Pollinations classic: 1 запрос в 31 с на IP, одна модель. LLM7: 30 RPM анонимно, набор моделей меняется (берётся из /models). Запросы идут внешним сервисам: чувствительное в них не класть.

## Старшие советники по рисованию (V + A2, проверено вживую 2026-11-25)
Реестр `state/advisors_external.json`, поле `roles`: `drawing_senior_gen`, `drawing_senior_critic`. Ключи в `state/secrets/advisors.env` (для бесплатных путей ниже не нужны). Только официальные API.
- Генерация: `POST 127.0.0.1:8793/v1/images/generations` `{"prompt","model":"auto|pollinations/flux|horde/","size":"768x768","response_format":"b64_json"(опц.)}` -> `data[0].path` (файл в state/advisor_images). Живой тест: pollinations/flux ok ~9 с, AI Horde (анонимный ключ 0000000000, официальный) ok ~15 с.
- Критика: `POST 127.0.0.1:8793/v1/images/critique` `{"image_path"|"image_b64","prompt","model":"auto|kilo/<vision>"}` -> `critique` {score, prompt_match, composition, anatomy, light_color, issues, fixes, improved_prompt} и `text`. Живой тест: kilo/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free ok ~15 с (score 5, нашёл расхождение с промптом). nemotron-3.5-super-vl: пустой ответ, статус weak.
- Приватность: наружу уходят только картинки, сгенерированные советниками (хеш в .index). Фото владельца и пути вне advisor_images дают 403 (проверено), пока в cfg нет `allow_external_images=true` И в запросе `x_nox_allow_image=true`. Промпт проходит санитайзер.
- Цикл для студии: gen -> critique -> `improved_prompt` -> gen (1-2 круга). Лимиты: pollinations ~1 запрос/20 с на IP, horde очередь, kilo 150/ч.
- С ключом (опционально, статус need_key): google/gemini-2.5-flash, groq llama-4-scout, openrouter qwen2.5-vl:free.
