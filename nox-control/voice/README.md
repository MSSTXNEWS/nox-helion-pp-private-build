# NOX voice (блок «Голос», D12-04/05/06/08/21)

Голос по HTTP: **STT** (faster-whisper, RU/ES) + конец реплики (`community/smart_turn.py`), **TTS** (XTTS -> запасной Piper) по кусочкам,
**voice_loop** (аудио -> STT -> чат -> TTS -> воспроизведение, барж-ин). Серверы и тесты - только stdlib; тяжёлые пакеты подключаются лениво,
`/health` честно показывает, что есть, а чего нет.

## Порты
STT **8093**, TTS **8094** (env `NOX_STT_PORT`/`NOX_TTS_PORT`). Запрошенные 8091/8092 не использованы: **8091 занят nox-bridge** (и 8098, 8080-8083 заняты). `start_voice.sh` проверяет занятость порта и отказывается стартовать поверх чужого процесса.

## Установка и запуск (сервер S1)
```bash
voice/install_deps.sh        # идемпотентно; venv ~/.nox-voice-venv; в конце список "поставилось / не поставилось"
voice/start_voice.sh all     # nohup, логи ~/nox-voice-logs, pid ~/.nox-voice-run; stop_voice.sh останавливает
curl 127.0.0.1:8093/health ; curl 127.0.0.1:8094/health
python3 voice/voice_loop.py --input file:q.wav --output file:/tmp/out --once     # без микрофона
python3 -m unittest voice.test_voice                                              # тесты (из nox-control/)
```
Пакеты: `numpy faster-whisper ctranslate2 onnxruntime piper-tts torch(CPU) coqui-tts` (+ системные `ffmpeg`, для микрофона `alsa-utils`).
Для Python 3.12 нужен именно **`coqui-tts`** (форк, модуль `TTS`): оригинальный `TTS` на 3.12 не ставится.

## STT (`stt_server.py`)
- `POST /transcribe?language=ru|es&words=1&format=auto` - тело WAV / raw PCM16 16 кГц / webm,opus,ogg,mp3 (только с `ffmpeg`). Ответ: `language`, `language_probability`, `text`, `segments[].words[]` (метки времени слов).
- Язык без `language` выбирается только среди `NOX_STT_LANGS` (по умолчанию `ru,es`).
- Поток: `POST /stream/start` -> `POST /stream/<id>/chunk` (PCM16 16 кГц или WAV, по 100-500 мс; ответ содержит события) -> `GET /stream/<id>/events?after=N`, `POST /stream/<id>/finish|close`.
  События: `speech_start`, `partial` (раз в `NOX_STT_PARTIAL_INTERVAL`, 1.5 с; `0` = выкл.), затем при конце реплики **`final` -> `end_of_turn`** (`reason`: `smart_turn` | `max_len` | `finish`).
  Чанки webm/opus по одному не декодируются (нужен контейнер целиком) - для потока шлите PCM16.
- Конец реплики: `smart_turn.heuristic_analyze` (или ONNX, если задан `NOX_SMART_TURN_MODEL` и есть onnxruntime). Пороги env / `{"turn": {...}}` в `/stream/start`:
  `NOX_TURN_BASE_PAUSE`=0.6, `NOX_TURN_MIN_SPEECH`=0.15, `NOX_TURN_MIN_TRAILING`=0.3, `NOX_TURN_ONNX_THRESHOLD`=0.5, `NOX_TURN_MAX_UTTERANCE`=30, `NOX_TURN_WINDOW`=8, `NOX_TURN_SPEECH_START_MS`=250.
- Модель: `NOX_STT_MODEL` (small; `large-v3` по желанию), `NOX_STT_DEVICE` (cpu|cuda), `NOX_STT_COMPUTE` (int8; на GPU float16), `NOX_STT_THREADS` (8), `NOX_STT_BEAM` (1), `NOX_STT_MODEL_DIR`, `NOX_STT_PRELOAD` (1).

## TTS (`tts_server.py`)
- Сессия потокового текста (под токены LLM): `POST /session {lang}` -> `POST /session/<id>/text {text, final}` (много раз) -> `GET /session/<id>/audio?format=sse|pcm|wav`.
  Сегментатор режет текст на лету по предложениям (аббревиатуры, десятичные, `1.` в списках, блоки ``` пропускаются; первая фраза режется по запятой уже после ~30 символов; длинное - по `NOX_TTS_MAX_CHARS`=180), аудио отдаётся, как только готова первая фраза.
- Весь текст сразу: `POST /synth {text, lang, format}`.
- Выход фиксирован: PCM16 mono `NOX_TTS_OUT_RATE` (24000); любой бэкенд ресемплится. SSE-события: `audio` (`pcm_b64`, `text`, `backend`, `seq`), `error`, `end` | `cancelled`.
- **STOP**: `POST /session/<id>/stop` или `POST /stop {session?}` (без session - все); очередь чистится, новые фразы не синтезируются. Разрыв соединения клиентом тоже отменяет сессию.
- Очистка текста: markdown, код, URL, e-mail, эмодзи, аббревиатуры (т.д., p. ej., ИИ, GPU...), числа/проценты/единицы -> слова (RU/ES).
- Бэкенды (`NOX_TTS_BACKENDS`=`xtts,piper`): **XTTS** (`NOX_XTTS_SPEAKER_WAV` - образец для клонирования голоса, `NOX_XTTS_SPEAKER`, `NOX_TTS_DEVICE`=cpu, `NOX_XTTS_MODEL`); **Piper** (`NOX_PIPER_BIN`, `NOX_PIPER_MODEL_RU/_ES/`). Нет/сбой XTTS -> автоматически Piper; упавший бэкенд отключается на `NOX_TTS_COOLDOWN` (120 с); если не вышло ни у одного - событие `error` с причинами по каждому.

## voice_loop (`voice_loop.py`)
`--input mic|stdin|file:PATH`, `--output play|file:DIR|null`, `--stt-url`, `--tts-url`, `--chat-url` (по умолчанию nox-bridge `:8091/v1/chat/stream`), `--chat-format nox|openai|plain`, `--lang`, `--no-barge-in`, `--barge-min-ms`, `--realtime`, `--once`.
Барж-ин: событие `speech_start` (>= `--barge-min-ms` речи) во время озвучки -> стоп TTS-сессии, остановка воспроизведения, отмена потока чата; сказанное затем становится новой репликой. На колонках (эхо) возможны ложные срабатывания: используйте наушники или `--no-barge-in` (полудуплекс - микрофон молчит, пока говорит ассистент).

## Честные ограничения
- **Скачивания**: модели Whisper (small ~0.5 ГБ, large-v3 ~3 ГБ), XTTS v2 (~1.8 ГБ, лицензия CPML - принять: `NOX_XTTS_AGREE_TOS=1`), голоса Piper (с HuggingFace) не входят в репозиторий; без выхода к HuggingFace/PyPI сервисы стартуют, но `/health` покажет `ready:false`, а запросы вернут 503/`error`.
- **GPU**: VRAM занята слоями GLM, поэтому по умолчанию всё на CPU. XTTS на CPU медленнее реального времени для длинных фраз (латентность первой фразы - секунды); large-v3 на CPU заметно медленнее small. Для скорости: Piper первым (`NOX_TTS_BACKENDS=piper,xtts`), `small`/`int8`.
- Реальные модели в этой сборке не запускались (нет доступа к скачиванию): тесты используют поддельные транскрайбер/бэкенды; API faster-whisper 1.2.1 и CLI piper-tts сверены с установленными пакетами.
- Smart Turn ONNX-модель не скачивается скриптом; без неё работает эвристика (VAD по энергии, порог шума адаптивный).
- Числа не склоняются по падежам («от 16 ГБ» -> «от шестнадцать гигабайт»), порядковые («1-й») не поддерживаются. Эхо-подавления нет. Нет аутентификации: серверы слушают `127.0.0.1`.
