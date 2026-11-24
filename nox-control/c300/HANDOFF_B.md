# HANDOFF исполнителя B (NOX HELION, ТЗ «Топ-10 WOW») — 2026-11-24
## Сделано (задача 1: голос, версия «конвейер ударений/пауз/чисел»)
- venv /workspace/nox/voice2_venv (py3.10): torch(cpu), pymorphy3, num2words, ruaccent 1.6, onnxruntime, scipy, silero-пакеты. ~1.2 ГБ.
- Модели /workspace/nox/voice_models/silero/: v5_ru.pt (TTS), v2_4lang_q.pt (silero-te, пунктуация). Лицензия Silero: CC BY-NC-SA 4.0 (только личное/некоммерческое) — отметить в отчёте. RUAccent — модели с HF (кэш ~/.cache/huggingface).
- Сервис TTS2 :8095 (127.0.0.1): /workspace/nox/c300_voice/voice2/{tts2_server.py,ru_norm.py,test10.py}; лог /workspace/nox/svc/logs/tts2.log. Автозапуск: строка добавлена в /workspace/nox/svc/start_extra.sh (бэкап .bak_b_1).
- Прокси /svc/tts2/ (запись в svc_registry.json, бэкап .bak_b_1): GET health, voices; POST prep, synth {text,voice,normalize,punct,accent,pauses,intonation,rate,pitch,format:wav|json}.
- Голоса: aidar (мужской, основной NOX), eugene (мужской), baya/kseniya/xenia (женские). Piper :8094 — запасной (не тронут).
- Конвейер: ru_norm (числа с падежами/родом, годы «в … году», даты, время, %, суммы, единицы, диапазоны, римские, телефон, латиница, сокращения; NOX→Нокс) -> silero-te (знаки, авто если нет .!? и >50 симв.) -> RUAccent (ударения «+», ё, омографы замок/зАмок) -> SSML (break запятая 180мс, тире 350, двоеточие 300, ; 320, вопрос/! просодия, rate/pitch) -> Silero.
- Тест 10 фраз (до/после) прогнан: wav в /workspace/nox/web/site/qa/voice2/pNN_{before,after}.wav; лог /workspace/nox/svc/logs/tts2_test.log. Примеры после: «в 1996 году»->«в тысяча девятьсот девяносто шестом году»; «21 ноября»->«двадцать первого ноября»; «24.11.2026»->«двадцать четвёртое ноября две тысячи двадцать шестого года»; «48 ГБ»->«сорок восемь гигабайт»; «$1 299»->«тысяча двести девяносто девять долларов»; «10–20 минут»->«от десяти до двадцати минут».
- UI: voice.html (бэкап voice.html.bak_b_1) + nox-voice-x.js/.css: голос, ползунки скорость/высота, переключатели (числа, ударения, паузы, интонация, знаки), «Прослушать пример» (10 трудных фраз), «До/после».
## В процессе / не сделано
- Исправление ru_norm (на 85% -> «на восемьдесят пять процентов») задеплоено в dep5 (проверить прогоном test10.py).
- Скриншоты voice.html (ПК 1440x900, моб 390x844) и qa/rework/voice.fixed — НЕ сделаны. Playwright на S1: python playwright + chromium в /workspace/nox/tools/ms-playwright (см. /workspace/nox/qa_audit.py стр. 34-52).
- Kokoro: русского нет -> не ставил; Chatterbox не ставил. Опционально проверить runorm (pip) как нейро-замену.
## Следующие шаги (порядок ТЗ)
2 Музыка ACE-Step 1.5 (диск свободно ~22 ГБ, держать запас >=4; VRAM своб. ~15 ГБ; текущий music.html ждёт сервис :8102 /music/*; nox-music-x.js уже есть) -> вкладка «Создать трек». 3 photo.html Qwen-Image-Edit (только если влезает). 4 studio.html лента/пресеты через /img/generate. 5 knowledge.html Khoj (оценить), Letta только отчёт. 6 news.html (FreshRSS без входа — честное состояние). 7 пустые состояния cinema/tv/music. Затем ревью страниц A и .fixed.
## Команды
- Запуск скрипта: положить nox-control/c300/b_<имя>.sh, /home/claude/run_b.sh b_<имя>.sh (commit+push+dispatch, ищет run по "C300: имя"); лог: gh run view <id> --repo MSSTXNEWS/nox-helion-pp-private-build --log | cut -f3-. Очередь общая с A (concurrency), запуск 1-3 мин, не чаще 1/мин; долгие шаги — nohup setsid + проверка позже.
- Файлы на сервер: base64 в heredoc скрипта. Исходники локально: /home/claude/voice2/, /home/claude/site/.
- Диск в конце работы: ~22 ГБ свободно (/workspace).
