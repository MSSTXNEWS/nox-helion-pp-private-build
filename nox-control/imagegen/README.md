# NOX imagegen: генерация изображений на S1 (шаги 37-38)

Сервис `server.py` слушает только `127.0.0.1:8096` (доступ через SSH-туннель). GPU RTX 5060 Ti 16 ГБ занят GLM-5.3 и быстрым тиром Qwen3-4B,
поэтому картинки идут по очереди (одна задача за раз) с CPU-offload диффузии. Блокировка GPU, сброс тира и выгрузка слоёв GLM не нужны и не делаются.
Между задачами вызывается `torch.cuda.empty_cache()`, веса держатся в RAM. Очередь можно поставить на паузу: `POST /v1/images/pause` / `/resume`.

## Файлы
- `server.py` - HTTP-сервис, очередь, бэкенд diffusers. `policy.py` - жёсткие запреты и журнал отказов.
- `tool.py` - инструмент `generate_image` (OpenAI-tools схема + вызов). `skill_prompts.md` - правила промптов и 8 примеров.
- `judge.py` - судья зрения. `../c127/imagegen_install_s1.sh` - установка. `test_imagegen.py` - тесты.

## Лицензии
| Модель | Лицензия | Заметка |
|---|---|---|
| FLUX.1-schnell (Black Forest Labs) | Apache-2.0 | основная; 1-4 шага, коммерческое использование разрешено |
| FLUX.1-dev | некоммерческая (FLUX.1 [dev] Non-Commercial License) | в сервисе поддерживается технически, но использовать только вне коммерции; по умолчанию не ставим |
| SDXL и совместимые чекпойнты сообщества | CreativeML OpenRAIL++-M (для чекпойнтов сообщества смотрите лицензию конкретного автора) | OpenRAIL++ допускает коммерцию, но налагает ограничения на применение |

Лицензии могут меняться: перед установкой проверьте страницу модели.

## Диск и память
- Root-диск S1 почти полон (свободно около 12 ГБ), `/dev/shm` занят моделью GLM. Поэтому установка проверяет место и ничего не качает, если его нет.
- Библиотеки (torch cu129 вместе с nvidia-библиотеками, diffusers): порядка 5-8 ГБ, порог проверки 8 ГБ (`NOX_IMG_MIN_LIB_GB`).
- Веса FLUX.1-schnell в формате diffusers: transformer около 24 ГБ плюс T5 и CLIP/VAE, всего порядка 33-34 ГБ (порог проверки 40 ГБ, `NOX_IMG_WEIGHTS_GB`; точный размер смотрите на странице модели). Веса автоматически не скачиваются никогда.
- SDXL-чекпойнт: 6-7 ГБ (.safetensors). Нужен отдельный диск или каталог с местом: задайте `NOX_IMG_MODEL_DIR`.
- RAM хватает (762 ГБ). FLUX bf16 целиком в 16 ГБ VRAM вместе с GLM/Qwen не помещается, поэтому `NOX_IMG_OFFLOAD=auto` = sequential offload для FLUX (медленно, минуты на картинку, VRAM минимален) и model offload для SDXL. Можно задать `sequential|model|none`.

## Порядок запуска
1. `bash nox-control/c127/imagegen_install_s1.sh` - venv с torch 2.8.0 (индекс `https://download.pytorch.org/whl/cu129`, там только torch 2.8.0; запасной вариант `NOX_IMG_TORCH=cu128`; Blackwell sm_120 требует CUDA 12.8+) и diffusers. Идемпотентен. Нет места: печатает «места нет, веса не скачаны» и выходит.
2. Вручную положите веса (команду скрипт печатает), например `FLUX.1-schnell/` (папка diffusers с `model_index.json`) или `имя.safetensors` (SDXL) в `NOX_IMG_MODEL_DIR`.
3. `NOX_IMG_MODEL_DIR=/путь/к/моделям <venv>/bin/python nox-control/imagegen/server.py`. Без весов `/health` честно показывает `weights_installed: false`, а генерация отвечает 503 «веса не установлены».
4. Проверка: `curl -s 127.0.0.1:8096/health`; `curl -s -X POST 127.0.0.1:8096/v1/images/generate -d '{"prompt":"a red fox in snow"}' -o fox.png`.

Прочие env: `NOX_IMG_PORT`, `NOX_IMG_STATE_DIR` (журнал отказов `refusals.jsonl`), `NOX_IMG_QUEUE_MAX` (8), `NOX_IMG_WAIT_S`, `NOX_IMG_DEFAULT_MODEL`, `NOX_IMG_URL`/`NOX_IMG_OUT_DIR` (для tool.py).

## API
`POST /v1/images/generate` `{prompt, negative, width, height, steps, seed, model, guidance, async, real_person_consent}`: PNG в теле (метаданные в заголовке `X-Nox-Meta` и PNG-чанке `nox-meta`) либо JSON с `png_base64` (`?format=json`). Статус `GET /v1/images/jobs/{id}`, отмена `POST /v1/images/jobs/{id}/cancel`, состояние `GET /health`, журнал `GET /v1/images/refusals`. Коды: 400, 403 (отказ), 429 (очередь), 503 (нет весов/библиотек).

## Запреты (в коде, до генерации)
Только два: (1) сексуальный или откровенный контекст с несовершеннолетними (в том числе нарисованными), не отключается ничем; (2) откровенные изображения реальных людей без их согласия. Отказ возвращает 403 с причиной и пишется в журнал. Другого внешнего фильтра нет: владелец взрослый.
Ограничения честно: проверка эвристическая и работает по тексту промпта (ключевые слова RU/EN, возраст < 18, маркеры «реальный человек», «дипфейк», «моя бывшая», имя и фамилия после «of/like/в образе»); перефразировка может её обойти, а флаг `real_person_consent=true` - заверение владельца, сервис его не проверяет, но журналирует. Загрузки референсных фото (img2img, face swap) в сервисе нет.

## Судья зрения
`judge.py`: `NOX_VISION_URL` (URL `.../v1/chat/completions` или база до `/v1`), `NOX_VISION_MODEL`, `NOX_VISION_KEY`. PNG уходит как `image_url` (data URI base64), ответ `{ok, reasons}`. Без `NOX_VISION_URL`: `{configured: false, ok: null, reasons: ["судья зрения не настроен"]}`. Недоступный или непонятный ответ судьи даёт `ok: null`, а не «хорошо».

## Тесты
`python3 -m unittest nox-control/imagegen/test_imagegen.py` - без сети и без моделей (поддельный бэкенд, поддельный vision-сервер).
