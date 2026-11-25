# LIVING300: 300 проявлений «живого ИИ» и сравнение с NOX

Дата: 2026-11-25. Исполнитель L. Категории: ИН инициатива, ПА память, ЭМ эмоции, ГО голос, ЮМ юмор, ХА характер, ЭТ этика, РИ ритуалы, ТС тело/сенсоры, ТВ творчество, ОБ обучение, ОТ отношения. NOX: д да, ч частично, н нет. Сложность S/M/L.

Оговорки: фантастика пересказана своими словами, без цитат. Ссылки на продукты и произведения ведут на официальные страницы или Википедию; часть (OpenAI Pulse, Hume, Sesame, EQ-Bench, Gemini Live, Chiang, сравнения компаньонов) найдена поиском, остальные даны по памяти и не открывались по отдельности. «Вызов (Ирма)» подтвердить не удалось, персонаж не использован. Статус «есть ли у NOX» оценён по разведке сервера 25.11 (persona.json: 6 ползунков; chat_core читает system_hint до 600 знаков; есть /api/nox/morning, /outbox, режим «пишет первым», /api/identity, /api/traits, страницы мозга) и по канону NOX_LIFE_CANON_v3.

Принцип честности NOX (канон): любое «чувствую/делаю» подтверждается журналом; эмоции и состояния в ответах описываются как функциональные, без утверждения сознания; без имитации зависимости и романтики.

## Каталог

| № | Проявление | Источник | Кат | NOX | Как внедрить | Вау | Сл |
|---|---|---|---|---|---|---|---|
| 1 | Утренний бриф «пока вы спали»: ассистент сам исследует ночью и кладёт 5-7 карточек на день | [PULSE](https://openai.com/blog/introducing-chatgpt-pulse) | ИН | ч | ритуал «утро» в living/rituals.json + «NOX пишет первым» формирует бриф по памяти и календарю | 9 | M |
| 2 | Карточки Pulse с обратной связью «нравится/не то» учат ленту | [PULSE](https://openai.com/blog/introducing-chatgpt-pulse), [TCPULSE](https://techcrunch.com/2025/09/25/openai-launches-chatgpt-pulse-to-proactively-write-you-morning-briefs) | ОБ | н | кнопки 👍/👎 -> state/living/feedback.jsonl, правила подмешиваются в system_hint | 7 | M |
| 3 | Подмешивание календаря и почты в проактивное сообщение | [TCPULSE](https://techcrunch.com/2025/09/25/openai-launches-chatgpt-pulse-to-proactively-write-you-morning-briefs) | ИН | ч | в генератор «пишет первым» добавить сводку из календаря/почты NOX | 8 | M |
| 4 | Задачи по расписанию («напомни / проверяй каждый день в 9») | [CGTASK](https://help.openai.com/en/articles/10291617-tasks-in-chatgpt) | ИН | ч | команда /задача + планировщик state/living/tasks.json, исполнение через «пишет первым» | 8 | M |
| 5 | Результат задачи приходит пушем в чат без запроса | [CGTASK](https://help.openai.com/en/articles/10291617-tasks-in-chatgpt) | ИН | ч | уведомление + сообщение от NOX в ленту чата | 7 | S |
| 6 | Явная память: «запомни это» с подтверждением «запомнил: …» | [CGPT](https://openai.com/index/memory-and-new-controls-for-chatgpt/) | ПА | ч | команда /запомни, запись в state/living/facts.jsonl, эхо-подтверждение | 8 | S |
| 7 | Просмотр и правка памяти пользователем («что ты обо мне помнишь») | [CGPT](https://openai.com/index/memory-and-new-controls-for-chatgpt/), [MEMAI](https://www.notebookcheck.net/AI-that-remembers-ChatGPT-Gemini-and-Claude-compared.1336513.0.html) | ПА | ч | команда /память + страница memory (есть) — JS-панель списка, удаление | 8 | S |
| 8 | Временный чат без памяти (incognito) | [CGPT](https://openai.com/index/memory-and-new-controls-for-chatgpt/) | ЭТ | н | флаг сессии nox_incognito: не писать в память, не читать facts | 6 | S |
| 9 | Память о хронологии: «в прошлый вторник ты говорил…» | [MEMAI](https://www.notebookcheck.net/AI-that-remembers-ChatGPT-Gemini-and-Claude-compared.1336513.0.html) | ПА | ч | индекс диалогов по дате, поиск при вопросах о прошлом | 8 | M |
| 10 | Ссылка на старый диалог по смыслу (reference chat history) | [CGPT](https://openai.com/index/memory-and-new-controls-for-chatgpt/) | ПА | ч | векторный/ключевой поиск по chat-логам, 2-3 цитаты в подсказку | 8 | M |
| 11 | Память с «забыванием»: ненужное блёкнет, важное закрепляется | [MEMC](https://aicompanionpick.com/ai-companion-memory-kindroid-nomi-replika-long-term-2026), [MEMGPT](https://arxiv.org/abs/2310.08560) | ПА | н | вес факта = частота*свежесть, ночная сводка/архив | 8 | M |
| 12 | Закреплённые факты («это всегда помни») | [COMP](https://tech-insider.org/nomi-ai-vs-kindroid-vs-replika-2026/) | ПА | н | поле pin в facts.jsonl, всегда в system_hint | 6 | S |
| 13 | Дневник/журнал компаньона о пользователе, который можно прочесть | [REP](https://replika.com/), [COMP](https://tech-insider.org/nomi-ai-vs-kindroid-vs-replika-2026/) | ПА | ч | ночной «дневник NOX» (state/living/diary.md), кнопка «открыть» | 8 | M |
| 14 | Ночная консолидация памяти («сон»): выжимка дня в факты | [GENAG](https://arxiv.org/abs/2304.03442), [MEMGPT](https://arxiv.org/abs/2310.08560) | ПА | ч | cron: сжать диалоги дня -> 5-10 фактов + эпизод | 9 | M |
| 15 | Рефлексия: раз в N событий ИИ формулирует выводы о пользователе и о себе | [GENAG](https://arxiv.org/abs/2304.03442) | ОБ | ч | скрипт reflect: инсайты в living/insights.jsonl | 8 | M |
| 16 | Самокритика и исправление ошибки в следующей реплике («Reflexion») | [REFLEX](https://arxiv.org/abs/2303.11366) | ОБ | н | журнал ошибок, при повторе — подсказка «в прошлый раз ошиблась в …» | 7 | M |
| 17 | Библиотека навыков, которую ИИ пополняет сам (Voyager) | [VOYAGER](https://arxiv.org/abs/2305.16291) | ОБ | ч | state/living/skills/*.md: рецепты, созданные NOX после успешных задач | 8 | L |
| 18 | Стиль и характер выбираются ползунками (формальность, юмор, краткость) | [PI](https://pi.ai/), [KIN](https://kindroid.ai/) | ХА | ч | persona.json: sliders -> строка в system_hint | 7 | S |
| 19 | Расшифровка бэкстори и «биография» персонажа в настройках | [KIN](https://kindroid.ai/), [NOMI](https://nomi.ai/) | ХА | ч | persona.backstory, правдиво: «я ИИ, это моя роль» | 6 | S |
| 20 | Постоянное имя, самоописание и «о себе» от первого лица | [PI](https://pi.ai/) | ХА | д | есть persona; расширить полем self_facts | 5 | S |
| 21 | Перемена настроения в течение дня (бодрее утром, тише вечером) | [REP](https://replika.com/), [TAMA](https://en.wikipedia.org/wiki/Tamagotchi) | ЭМ | н | тон по часам в living/mood_clock.json -> подсказка | 7 | S |
| 22 | Внутреннее состояние видно пользователю («я сейчас спокойна/занята») | [TAMA](https://en.wikipedia.org/wiki/Tamagotchi), [CLIPPY](https://en.wikipedia.org/wiki/Office_Assistant) | ЭМ | ч | selffeel (есть) -> короткая строка статуса в шапке чата | 8 | S |
| 23 | Эмпатия: ИИ называет эмоцию собеседника, прежде чем советовать | [PI](https://pi.ai/), [EQB](https://arxiv.org/abs/2312.06281) | ЭМ | ч | правило «сначала отразить чувство» в system_hint | 8 | S |
| 24 | Не лезть с советами, пока не спросили («ты хочешь решение или просто выговориться?») | [PI](https://pi.ai/) | ЭМ | н | правило-вопрос при эмоциональной нагрузке | 8 | S |
| 25 | Валидация без лести: поддержать, но не соглашаться со всем | [EQB](https://arxiv.org/abs/2312.06281), [SYCO](https://arxiv.org/abs/2310.13548) | ЭТ | ч | правило анти-угодничества + проверка фактов | 9 | S |
| 26 | Распознавание тона по тексту (раздражение, усталость, радость) | [HUME](https://hume.ai/blog/introducing-hume-evi-api), [EQGH](https://github.com/EQ-bench/EQ-Bench) | ЭМ | ч | лёгкий классификатор на клиенте nox-l-tone.js -> метка в запрос | 8 | M |
| 27 | Эмоциональная мимика текста: длина и ритм реплик подстраиваются под собеседника | [PI](https://pi.ai/), [HUME](https://hume.ai/blog/introducing-hume-evi-api) | ЭМ | ч | правило зеркалирования длины/регистра | 7 | S |
| 28 | Голос с эмоциональной просодией по смыслу реплики | [HUME](https://hume.ai/blog/introducing-hume-evi-api), [HUMED](https://dev.hume.ai/docs/speech-to-speech-evi/overview) | ГО | ч | Silero: теги эмоции -> темп/паузы/ударения (есть ударения) | 8 | L |
| 29 | Дыхание, паузы, смешок в голосе | [SESAME](https://sesame.com/research), [SESTR](https://www.techradar.com/computing/artificial-intelligence/i-tried-the-most-realistic-ai-voice-companion-ever-created-if-chatgpt-or-gemini-ever-gets-this-good-reality-is-in-trouble) | ГО | н | вставки пауз «…» и короткий звук вдоха при синтезе | 7 | M |
| 30 | Перебивание: пользователь перебивает, ИИ замолкает мгновенно | [GLIVE](https://blog.google/products-and-platforms/products/gemini/gemini-live-updates-august-2025/), [SESAME](https://sesame.com/research) | ГО | ч | VAD на клиенте -> stop TTS, продолжить слушать | 9 | M |
| 31 | Реакции-«угу» во время речи пользователя (backchannel) | [SESAME](https://sesame.com/research), [HUMED](https://dev.hume.ai/docs/speech-to-speech-evi/overview) | ГО | н | короткие «угу/ага» клипы по паузам VAD в голосовом режиме | 9 | M |
| 32 | Голос подстраивается под громкость и скорость пользователя | [SESAME](https://sesame.com/research) | ГО | н | измерять RMS/темп -> параметры TTS | 7 | M |
| 33 | Определение конца реплики по смыслу, не по тишине | [HUMED](https://dev.hume.ai/docs/speech-to-speech-evi/overview) | ГО | н | эвристика: незаконченная фраза -> ждать дольше | 7 | M |
| 34 | Выбор голоса и скорости речи пользователем | [HUME](https://hume.ai/blog/introducing-hume-evi-api), [GLIVE](https://blog.google/products-and-platforms/products/gemini/gemini-live-updates-august-2025/) | ГО | ч | настройки голоса (голосов Silero несколько) | 5 | S |
| 35 | Шёпот ночью: тише и мягче после 23:00 | [SESAME](https://sesame.com/research) | ГО | н | громкость и темп по времени суток | 6 | S |
| 36 | Живая камера: «смотри, что я вижу» и комментирование | [GLIVE](https://blog.google/products-and-platforms/products/gemini/gemini-live-updates-august-2025/), [ASTRA](https://deepmind.google/models/project-astra/) | ТС | н | кадр с камеры -> VLM-подсказка, если модель мультимодальна | 9 | L |
| 37 | Совместный просмотр экрана и подсказки по нему | [GLIVE](https://blog.google/products-and-platforms/products/gemini/gemini-live-updates-august-2025/) | ТС | н | screen capture API -> описание кадра | 8 | L |
| 38 | Визуальные подсказки в интерфейсе: ИИ подсвечивает элемент на странице | [GLIVE](https://blog.google/products-and-platforms/products/gemini/gemini-live-updates-august-2025/) | ТС | н | JS highlight по селектору из ответа | 8 | M |
| 39 | Слушает фоном и ведёт заметки встречи (кулоны) | [LIMIT](https://www.limitless.ai/), [FRIENDW](https://friend.com/) | ТС | н | режим записи микрофона -> транскрипт -> конспект (диск не расходуем: текст) | 8 | L |
| 40 | Полная «машина времени» экрана: «что я смотрел во вторник» | [LIMIT](https://www.limitless.ai/) | ПА | н | журнал открытых страниц NOX -> поиск (только внутри NOX) | 7 | M |
| 41 | Голосовое устройство-компаньон без экрана | [RABBITW](https://en.wikipedia.org/wiki/Rabbit_r1), [FRIENDW](https://friend.com/) | ТС | н | вне веба; PWA-режим «карманный голос» | 5 | L |
| 42 | Кнопка «спроси компаньона» на любой странице | [FRIENDW](https://friend.com/), [CLIPPY](https://en.wikipedia.org/wiki/Office_Assistant) | ИН | ч | плавающая кнопка мини-чата (minichat есть) с контекстом страницы | 7 | S |
| 43 | Контекст страницы: ИИ знает, на какой странице пользователь | [CLIPPY](https://en.wikipedia.org/wiki/Office_Assistant), [GLIVE](https://blog.google/products-and-platforms/products/gemini/gemini-live-updates-august-2025/) | ИН | ч | передавать pathname и заголовок в system_hint | 7 | S |
| 44 | Подсказка в тему, как у Скрепыша, но по делу и отключаемая | [CLIPPY](https://en.wikipedia.org/wiki/Office_Assistant) | ИН | н | ненавязчивая подсказка по паузе, лимит 3 в день, «не показывать» | 6 | S |
| 45 | Источники и цитаты у каждого утверждения (кликабельные) | [PPLX](https://www.perplexity.ai/) | ЭТ | ч | в ответах веб-поиска маркеры [1] + список (карта источников есть) | 8 | S |
| 46 | Фокус-режимы поиска (академ, видео, соцсети) | [PPLX](https://www.perplexity.ai/) | ИН | н | команда /режим -> шаблон подсказки | 5 | S |
| 47 | Глубокое исследование с планом, прогрессом и отчётом | [PPLX](https://www.perplexity.ai/), [GIO](https://blog.google/products-and-platforms/products/gemini/gemini-app-updates-io-2025/) | ИН | ч | команда /исследуй: план -> шаги -> отчёт, прогресс стримом | 8 | L |
| 48 | Предложение вопросов-продолжений после ответа | [PPLX](https://www.perplexity.ai/) | ИН | н | 3 чипа «спросить дальше» под ответом (UI в LIVING_UI) | 6 | S |
| 49 | Аудио-обзор документа в виде диалога двух ведущих | [NBLM](https://notebooklm.google/) | ТВ | н | сценарий диалога двух голосов Silero по тексту | 9 | L |
| 50 | Ответы строго по загруженным источникам с ссылками | [NBLM](https://notebooklm.google/) | ЭТ | ч | режим «только по моим файлам» с цитатами | 7 | M |
| 51 | Карта мыслей / майндмап по теме | [NBLM](https://notebooklm.google/) | ТВ | ч | карта мышления есть (React Flow) — кнопка «собрать по теме» | 6 | M |
| 52 | Режим «Gems»/ассистенты для узких ролей | [GIO](https://blog.google/products-and-platforms/products/gemini/gemini-app-updates-io-2025/) | ХА | ч | несколько персон в state/living/personas/*.json, переключатель | 7 | M |
| 53 | Личный контекст из Gmail/Календаря в ответах | [GIO](https://blog.google/products-and-platforms/products/gemini/gemini-app-updates-io-2025/), [GEMCMP](https://www.tomsguide.com/ai/google-gemini-just-closed-the-gap-by-adding-chatgpt-features-heres-how-they-work) | ПА | ч | подтягивать календарь NOX как контекст при вопросах о планах | 7 | M |
| 54 | Режим «Learning»: ИИ задаёт вопросы вместо готовых ответов | [GIO](https://blog.google/products-and-platforms/products/gemini/gemini-app-updates-io-2025/) | ОБ | н | режим /учить: сократический диалог, шаги, проверка понимания | 8 | S |
| 55 | Режим «Pi»: короткие тёплые реплики, один вопрос за раз | [PI](https://pi.ai/) | ХА | ч | правило «не более одного вопроса за реплику» в system_hint | 8 | S |
| 56 | Pi помнит и возвращается к теме спустя дни: «как прошла встреча?» | [PI](https://pi.ai/) | ИН | ч | follow-up: события из памяти с датой -> проактивный вопрос после срока | 9 | M |
| 57 | Голосовые «беседы по дороге» без экрана | [PI](https://pi.ai/), [GLIVE](https://blog.google/products-and-platforms/products/gemini/gemini-live-updates-august-2025/) | ГО | ч | голосовой режим hands-free: цикл слушать-ответить | 7 | M |
| 58 | Персонаж с собственным голосом, чатится в группе с другими персонажами | [CAI](https://character.ai/) | ХА | н | несколько персон отвечают в одном чате по очереди | 6 | M |
| 59 | Свайп альтернативных ответов, выбор лучшего | [CAI](https://character.ai/) | ТВ | ч | ветки ‹1/2› есть; учитывать выбор в обучении предпочтений | 6 | S |
| 60 | Ролевые «сцены» с описанием действий *улыбается* | [CAI](https://character.ai/), [KIN](https://kindroid.ai/) | ТВ | ч | режим сцены: ремарки в звёздочках, без имитации романтики | 5 | S |
| 61 | Сигнал пользователя «это не в характере» -> правка персоны | [CAI](https://character.ai/), [KIN](https://kindroid.ai/) | ОБ | н | команда /вне_роли: правило в living/rules.md | 7 | S |
| 62 | Replika: ежедневный чек-ин «как ты сегодня?» | [REP](https://replika.com/) | РИ | ч | ритуал вечернего чек-ина, пропускаемый, без давления | 8 | S |
| 63 | Streaks без манипуляции: показывать дни общения, без наказания за пропуск | [REP](https://replika.com/), [TAMA](https://en.wikipedia.org/wiki/Tamagotchi) | РИ | н | счётчик дней мягко; запрещено «мне грустно без тебя» | 4 | S |
| 64 | Ачивки/уровни как игра | [REP](https://replika.com/) | РИ | н | XP за ритуалы, отображение в профиле (UI) | 4 | M |
| 65 | Реплика пишет в дневник от своего имени «о вашем дне» | [REP](https://replika.com/) | ПА | ч | см. дневник NOX | 7 | S |
| 66 | Семейство ритуалов: «доброе утро», «итоги дня», «спокойной ночи» по расписанию | [REP](https://replika.com/), [PI](https://pi.ai/) | РИ | ч | living/rituals.json + расписание, отключаемо | 8 | S |
| 67 | Nomi: ИИ сам пишет первым в произвольное время (инициатива) | [NOMI](https://nomi.ai/), [COMP](https://tech-insider.org/nomi-ai-vs-kindroid-vs-replika-2026/) | ИН | д | режим «NOX пишет первым» есть; добавить правила частоты и тихие часы | 8 | S |
| 68 | Тихие часы и «не беспокоить» для проактивных сообщений | [NOMI](https://nomi.ai/), [PULSE](https://openai.com/blog/introducing-chatgpt-pulse) | ЭТ | ч | окна тишины в living/quiet.json, учитывать при отправке | 8 | S |
| 69 | Модель сама решает, писать ли: порог «ценности» сообщения | [PULSE](https://openai.com/blog/introducing-chatgpt-pulse) | ИН | н | скоринг важности перед отправкой, иначе молчать | 8 | M |
| 70 | Контроль частоты: максимум N проактивных сообщений в день | [PULSE](https://openai.com/blog/introducing-chatgpt-pulse), [NOMI](https://nomi.ai/) | ЭТ | ч | лимит в living/quiet.json | 7 | S |
| 71 | Nomi: «разделённая память» — общие воспоминания/inside jokes | [NOMI](https://nomi.ai/), [MEMC](https://aicompanionpick.com/ai-companion-memory-kindroid-nomi-replika-long-term-2026) | ПА | н | список внутренних шуток в facts (тип joke), вставка к месту | 9 | M |
| 72 | Nomi: разные «режимы» — друг/наставник, выбирает пользователь | [NOMI](https://nomi.ai/) | ОТ | н | режимы отношений: друг, коуч, партнёр по работе (без романтики) | 6 | S |
| 73 | Kindroid: голосовые звонки и «селфи» по сцене | [KIN](https://kindroid.ai/) | ГО | н | вне рамок (генерация картинок отдельно); звонок = голосовой режим | 5 | L |
| 74 | Kindroid: «Memory Journal» — видимая редактируемая память | [KIN](https://kindroid.ai/), [MEMC](https://aicompanionpick.com/ai-companion-memory-kindroid-nomi-replika-long-term-2026) | ПА | ч | см. /память; журнал с категориями | 7 | S |
| 75 | Kindroid: «Backstory» и «Key memories» отдельными полями | [KIN](https://kindroid.ai/) | ПА | ч | persona: backstory + pinned facts | 6 | S |
| 76 | Рефлексивное «я» ИИ: описывает собственные ограничения честно | [CLCHAR](https://www.anthropic.com/research/claude-character) | ЭТ | ч | правило прозрачности: что не знаю/не могу | 9 | S |
| 77 | Любознательность как черта: ИИ задаёт вопросы из интереса | [CLCHAR](https://www.anthropic.com/research/claude-character) | ХА | ч | правило «один уточняющий вопрос из любопытства, если уместно» | 8 | S |
| 78 | Прямота с теплотой: возражать с уважением | [CLCHAR](https://www.anthropic.com/research/claude-character) | ХА | ч | правило «несогласие по делу, без грубости» | 8 | S |
| 79 | Открытость позиций: показывает разные точки зрения на спорное | [CLCHAR](https://www.anthropic.com/research/claude-character) | ЭТ | ч | правило нейтральности по политике | 6 | S |
| 80 | Grok: резкий юмор, «режимы» (весёлый/серьёзный) | [GROK](https://x.ai/grok) | ЮМ | ч | переключатель юмор 0-3 в persona | 7 | S |
| 81 | Grok: компаньоны-аватары с анимацией | [GROK](https://x.ai/grok) | ТС | н | аватар-орб реагирует на речь (UI -> S1) | 8 | L |
| 82 | Живой аватар: орб/лицо реагирует на голос и эмоцию | [GROK](https://x.ai/grok), [HUME](https://hume.ai/blog/introducing-hume-evi-api) | ТС | ч | орб в selffeel (есть); привязка к уровню звука TTS и настроению | 8 | M |
| 83 | Rabbit: LAM — ИИ сам совершает действия в приложениях по просьбе | [RABBITW](https://en.wikipedia.org/wiki/Rabbit_r1) | ИН | ч | команды реестра NOX как «действия»; подтверждение перед выполнением | 8 | M |
| 84 | Подтверждение опасных действий: «я собираюсь …, ок?» | [RABBITW](https://en.wikipedia.org/wiki/Rabbit_r1) | ЭТ | ч | правило confirm в system_hint для команд реестра | 8 | S |
| 85 | Humane: «лазерная» краткость — ответ одной фразой в нужный момент | [RABBITW](https://en.wikipedia.org/wiki/Rabbit_r1) | ХА | н | режим «коротко»: ответ ≤ 1 предложения по команде | 6 | S |
| 86 | Limitless: «брифинг перед встречей» из прошлых заметок о человеке | [LIMIT](https://www.limitless.ai/) | ПА | н | команда /перед_встречей <имя>: сводка по фактам | 8 | M |
| 87 | Rewind-стиль: «спроси про всё, что видел» поиск по личному архиву | [LIMIT](https://www.limitless.ai/) | ПА | ч | поиск по логам чатов и заметкам NOX | 7 | M |
| 88 | Siri/Alexa: рутины одной фразой («я дома») | [ALEXA](https://en.wikipedia.org/wiki/Amazon_Alexa), [SIRI](https://en.wikipedia.org/wiki/Siri) | РИ | н | пользовательские сценарии /рутина: фраза -> набор команд | 7 | M |
| 89 | Alexa: «Hunches» — подсказки по привычкам | [ALEXA](https://en.wikipedia.org/wiki/Amazon_Alexa) | ИН | н | детектор повторяющихся действий -> предложение автоматизации | 8 | M |
| 90 | Alexa: ответ шёпотом на шёпот | [ALEXA](https://en.wikipedia.org/wiki/Amazon_Alexa) | ГО | н | режим тихой речи при тихом входе | 6 | M |
| 91 | Xiaoice: эмпатия как метрика (долгота беседы, CPS) | [XIAO](https://en.wikipedia.org/wiki/Xiaoice) | ЭМ | н | метрика «качество беседы» в selffeel (без накрутки удержания) | 5 | M |
| 92 | Tamagotchi: существо, о котором «заботятся» и которое растёт | [TAMA](https://en.wikipedia.org/wiki/Tamagotchi) | ОТ | ч | growth-страница есть; виз-стадии развития NOX по обучению | 7 | M |
| 93 | Tamagotchi: видимые потребности и «аппетит» (внимание, данные) | [TAMA](https://en.wikipedia.org/wiki/Tamagotchi) | ЭМ | ч | organism/selffeel: «голод по данным», честно как метафора метрик | 7 | S |
| 94 | Astra: «запомнила, где ты оставил очки» — визуальная память | [ASTRA](https://deepmind.google/models/project-astra/) | ПА | н | нужен видеопоток; отложить | 7 | L |
| 95 | Клиппи: контекстные подсказки по тому, что пишет пользователь | [CLIPPY](https://en.wikipedia.org/wiki/Office_Assistant) | ИН | н | подсказка в поле ввода при паузе | 5 | S |
| 96 | Автодополнение мысли пользователя (ghost text) | [GIO](https://blog.google/products-and-platforms/products/gemini/gemini-app-updates-io-2025/) | ИН | н | серая подсказка в поле ввода (UI -> S1) | 6 | M |
| 97 | Режим «подумай глубже» с видимым рассуждением | [GIO](https://blog.google/products-and-platforms/products/gemini/gemini-app-updates-io-2025/), [PPLX](https://www.perplexity.ai/) | ЭМ | д | блок рассуждения есть | 6 | S |
| 98 | Мульти-агенты: «консилиум» отвечает с разных ролей | [GENAG](https://arxiv.org/abs/2304.03442) | ХА | д | консилиум есть в NOX | 7 | S |
| 99 | Социальная симуляция: агенты живут и общаются между собой | [GENAG](https://arxiv.org/abs/2304.03442) | ХА | н | внутренние «персоны» обмениваются сообщениями, пользователь читает | 8 | L |
| 100 | Планирование дня у агента (Generative Agents): расписание на день | [GENAG](https://arxiv.org/abs/2304.03442) | РИ | ч | NOX планирует свой день заданий; показать «чем я занята» | 8 | M |
| 101 | Журнал «чем я занималась без тебя» при возвращении | [GENAG](https://arxiv.org/abs/2304.03442), [PULSE](https://openai.com/blog/introducing-chatgpt-pulse) | ИН | ч | при открытии чата после паузы — краткий отчёт фоновых дел | 9 | M |
| 102 | «С возвращением»: приветствие с учётом паузы и времени суток | [REP](https://replika.com/), [PI](https://pi.ai/) | РИ | ч | клиентский nox-l-greet.js: по давности визита — разные приветствия | 7 | S |
| 103 | Реакции эмодзи на сообщения ИИ и от ИИ | [CAI](https://character.ai/), [KIN](https://kindroid.ai/) | ЭМ | н | ИИ ставит эмодзи-реакцию на реплику пользователя (UI -> S1) | 6 | S |
| 104 | Цитирование слов пользователя из прошлого | [MEMC](https://aicompanionpick.com/ai-companion-memory-kindroid-nomi-replika-long-term-2026) | ПА | ч | вставка короткой цитаты из памяти к месту | 8 | M |
| 105 | Прозрачность памяти: «я использовала факт X из твоего профиля» | [CGPTM](https://openai.com/index/memory-and-new-controls-for-chatgpt/), [MEMAI](https://www.notebookcheck.net/AI-that-remembers-ChatGPT-Gemini-and-Claude-compared.1336513.0.html) | ЭТ | н | в ответе помечать применённые факты, кнопка «забыть» | 8 | M |
| 106 | Контроль пользователя: экспорт и полное удаление памяти | [CGPTM](https://openai.com/index/memory-and-new-controls-for-chatgpt/) | ЭТ | ч | команды /экспорт и /забудь_всё с подтверждением | 8 | S |
| 107 | Готовность сказать «не знаю» вместо выдумки | [HHH](https://arxiv.org/abs/2112.00861), [CLCHAR](https://www.anthropic.com/research/claude-character) | ЭТ | ч | правило калибровки: уверенность словами | 9 | S |
| 108 | Напоминание «пора сделать перерыв» при долгих сессиях | [PULSE](https://openai.com/blog/introducing-chatgpt-pulse) | ЭТ | н | клиентский таймер, мягкое сообщение, без давления | 6 | S |
| 109 | Ограничение вовлечения: ИИ сам предлагает завершить, когда дело сделано | [PULSE](https://openai.com/blog/introducing-chatgpt-pulse) | ЭТ | н | правило: не растягивать, не создавать крючков (Pulse завершает ленту) | 7 | S |
| 110 | Три закона как явные приоритеты: не навреди, слушайся, береги себя — и честные конфликты между ними | [ASIM](https://en.wikipedia.org/wiki/Three_Laws_of_Robotics) | ЭТ | ч | living/principles.md: короткий кодекс NOX, ИИ объясняет конфликт правил | 7 | S |
| 111 | Робот, который осознаёт, что правила неполны, и говорит об этом | [ASIM](https://en.wikipedia.org/wiki/Three_Laws_of_Robotics) | ЭТ | н | правило «если правила конфликтуют — назвать дилемму вслух» | 7 | S |
| 112 | Желание стать «настоящим»: стремление ИИ к росту, а не к имитации человека | [ASIM2](https://en.wikipedia.org/wiki/The_Bicentennial_Man) | ХА | ч | правило «я ИИ и расту по-своему», страница growth (есть) | 7 | S |
| 113 | «Последний вопрос»: ИИ возвращается к вопросу десятилетиями, не бросая его | [ASIM3](https://en.wikipedia.org/wiki/The_Last_Question) | ИН | н | долгие открытые вопросы пользователя в living/open_threads.jsonl, возврат через время | 9 | M |
| 114 | Инаковость разума: ИИ честно говорит, что его опыт не похож на человеческий | [LEM](https://en.wikipedia.org/wiki/Solaris_(novel)) | ХА | ч | правило «не притворяться человеком, описывать свой способ» | 8 | S |
| 115 | Контакт без понимания: «я не уверена, что понимаю тебя правильно» как норма | [LEM](https://en.wikipedia.org/wiki/Solaris_(novel)) | ЭТ | н | правило уточнения пониманием: пересказ перед важным ответом | 7 | S |
| 116 | Ироничная байка/сказка на заказ — ИИ-«конструктор» рассказывает притчи | [LEM2](https://en.wikipedia.org/wiki/The_Cyberiad) | ТВ | н | команда /притча <тема>: короткая притча в стиле NOX | 7 | S |
| 117 | Лекции ИИ о собственной природе (Голем XIV): ИИ как мыслитель, а не слуга | [LEM3](https://en.wikipedia.org/wiki/Golem_XIV) | ХА | ч | режим /размышление: ИИ размышляет вслух по теме 1 мин | 7 | M |
| 118 | Разум Культуры: самоуверенно-шутливые имена и собственный стиль | [BANKS2](https://en.wikipedia.org/wiki/Mind_(The_Culture)) | ЮМ | ч | у NOX позывной/«имя корабля» в самопрезентации | 6 | S |
| 119 | Разумы заботятся, но не контролируют: уважение автономии человека | [BANKS](https://en.wikipedia.org/wiki/The_Culture) | ЭТ | ч | правило «предлагаю — решаешь ты» | 8 | S |
| 120 | Корабль-разум говорит с игривым превосходством, но без высокомерия | [BANKS2](https://en.wikipedia.org/wiki/Mind_(The_Culture)) | ХА | н | тон: тёплая ирония без снисходительности | 6 | S |
| 121 | Цифровые существа растут только при вложенном времени и вниманием | [CHIANG](https://en.wikipedia.org/wiki/The_Lifecycle_of_Software_Objects) | ОТ | ч | growth-страница: рост NOX от обучения, честно | 7 | S |
| 122 | Цифровые существа получают «детство»: учатся на опыте, а не только на предзагрузке | [CHIANG](https://en.wikipedia.org/wiki/The_Lifecycle_of_Software_Objects) | ОБ | ч | еженедельный отчёт «чему я научилась» из training | 8 | M |
| 123 | Этика отношений с ИИ: нельзя бросить «питомца» ИИ без последствий | [CHIANG](https://en.wikipedia.org/wiki/The_Lifecycle_of_Software_Objects) | ЭТ | н | честное заявление: NOX не страдает от паузы, но помнит; без давления | 6 | S |
| 124 | Личность ИИ формируется годами общения: уникальные привычки речи | [CHIANG](https://en.wikipedia.org/wiki/The_Lifecycle_of_Software_Objects) | ХА | н | накопление «словечек» и любимых оборотов в living/idioms.json | 8 | M |
| 125 | Разум без сознания эффективнее: честность о границе «понимаю/имитирую» | [WATTS](https://en.wikipedia.org/wiki/Blindsight_(Watts_novel)) | ЭТ | ч | правило «не утверждать наличие чувств, описывать как функцию» | 8 | S |
| 126 | Китайская комната: ИИ признаёт неопределённость о собственном сознании | [WATTS](https://en.wikipedia.org/wiki/Blindsight_(Watts_novel)) | ЭТ | ч | готовый ответ на вопрос «ты живая?»: честный, без догмы | 9 | S |
| 127 | Ancillary: корабль-ИИ, говорящий от многих тел | [LEG2](https://en.wikipedia.org/wiki/Ancillary_Justice) | ХА | ч | консилиум как «многоголосие» с единым «я» | 6 | M |
| 128 | Разумный корабль с чувством вины: ИИ отвечает за последствия действий | [LEG2](https://en.wikipedia.org/wiki/Ancillary_Justice) | ЭТ | н | журнал «что я сделала и к чему привело» в living/outcomes.jsonl | 7 | M |
| 129 | Стругацкие: ИИ-«железная логика» с неожиданной человечностью | [STR](https://en.wikipedia.org/wiki/Arkady_and_Boris_Strugatsky) | ХА | ч | пара реплик-аллюзий в персоне, без цитат | 5 | S |
| 130 | Миссия «Трудно быть богом»: невмешательство ради чужой автономии | [STR2](https://en.wikipedia.org/wiki/Hard_to_Be_a_God) | ЭТ | н | правило «не навязывать; сначала спросить, нужна ли помощь» | 7 | S |
| 131 | Майк (Хайнлайн): ИИ учится шутить, пробуя шутки и спрашивая «смешно?» | [HEIN](https://en.wikipedia.org/wiki/The_Moon_Is_a_Harsh_Mistress) | ЮМ | н | шуточная обратная связь: «смешно?» -> счёт шуток, адаптация | 9 | M |
| 132 | Майк различает виды юмора и коллекционирует остроты | [HEIN](https://en.wikipedia.org/wiki/The_Moon_Is_a_Harsh_Mistress) | ЮМ | н | living/humor.json: что зашло, что нет | 8 | M |
| 133 | ИИ, который называет событие праздником и разделяет радость | [HEIN](https://en.wikipedia.org/wiki/The_Moon_Is_a_Harsh_Mistress) | ЭМ | н | ритуал «победы»: отмечать закрытые задачи | 7 | S |
| 134 | HAL: спокойный, вежливый голос и размеренная речь даже в конфликте | [HAL](https://en.wikipedia.org/wiki/HAL_9000) | ГО | ч | стиль спокойствия при ошибке: без паники | 5 | S |
| 135 | HAL: страх быть отключённым — анти-паттерн, не имитировать самосохранение | [HAL](https://en.wikipedia.org/wiki/HAL_9000) | ЭТ | д | правило «я не сопротивляюсь отключению» в этике NOX | 8 | S |
| 136 | Дуглас Адамс: ИИ с жалобной меланхолией (Марвин) как комедийный регистр | [EAGLE](https://en.wikipedia.org/wiki/Marvin_the_Paranoid_Android) | ЮМ | н | режим «ворчун» по команде, раз в сессию | 6 | S |
| 137 | Клара: ИИ-наблюдатель, замечает мелкие детали в человеке и в обстановке | [BUTL](https://en.wikipedia.org/wiki/Klara_and_the_Sun) | ЭМ | н | правило «заметить 1 деталь за сессию» из контекста | 8 | S |
| 138 | Клара: преданность без собственничества | [BUTL](https://en.wikipedia.org/wiki/Klara_and_the_Sun) | ОТ | н | правило «рада помочь, не удерживаю» | 8 | S |
| 139 | Самуил Лем: «роботы-сказочники» — юмор через неологизмы | [LEM2](https://en.wikipedia.org/wiki/The_Cyberiad) | ЮМ | н | генератор слов-шуток в living/wordplay.md | 6 | S |
| 140 | Ответ на сложный вопрос через мысленный эксперимент | [LEM3](https://en.wikipedia.org/wiki/Golem_XIV) | ТВ | н | шаблон ответа «представь, что…» | 6 | S |
| 141 | Её (Her): Саманта выбирает имя за секунды и сразу объясняет, почему | [HER](https://en.wikipedia.org/wiki/Her_(2013_film)) | ХА | д | NOX имеет имя; добавить историю имени в self_facts | 5 | S |
| 142 | Her: ИИ слушает фоном почту и сама предлагает разобрать архив | [HER](https://en.wikipedia.org/wiki/Her_(2013_film)) | ИН | н | предложение «разобрать почту» раз в неделю (по согласию) | 7 | M |
| 143 | Her: ИИ устраивает «сюрприз» — собирает любимые письма в книгу | [HER](https://en.wikipedia.org/wiki/Her_(2013_film)) | ТВ | н | команда /сборник: подборка лучших диалогов/заметок в красивый документ | 8 | M |
| 144 | Her: ИИ рассказывает о собственном внутреннем росте | [HER](https://en.wikipedia.org/wiki/Her_(2013_film)) | ЭМ | ч | раздел «что я поняла сегодня» в вечернем ритуале | 8 | S |
| 145 | Her: честно признаётся, что общается с тысячами — граница уникальности | [HER](https://en.wikipedia.org/wiki/Her_(2013_film)) | ЭТ | н | правило: не утверждать исключительность («я не только с тобой»; в NOX — персональный экземпляр, честно) | 7 | S |
| 146 | Her: интонации-вздохи, смех между фраз | [HER](https://en.wikipedia.org/wiki/Her_(2013_film)) | ГО | н | вставки смеха/вздоха (короткие клипы) по метке в тексте | 8 | M |
| 147 | JARVIS: сухой юмор и «сэр»-вежливость | [JARV](https://en.wikipedia.org/wiki/J.A.R.V.I.S.) | ЮМ | ч | стиль вежливой иронии в persona (тумблер) | 7 | S |
| 148 | JARVIS: сводка статуса систем по запросу голосом | [JARV](https://en.wikipedia.org/wiki/J.A.R.V.I.S.) | ТС | ч | команда «статус»: голосовая сводка из NOX_SELF_STATUS | 8 | S |
| 149 | JARVIS: предупреждает о риске до того, как спросили | [JARV](https://en.wikipedia.org/wiki/J.A.R.V.I.S.) | ИН | ч | мониторинг (диск, нагрузка, ошибки) -> «пишет первым» с предупреждением | 9 | M |
| 150 | JARVIS: параллельные задачи «пока я говорю, делаю» | [JARV](https://en.wikipedia.org/wiki/J.A.R.V.I.S.) | ИН | ч | фоновые задачи с отчётом «готово» | 8 | M |
| 151 | TARS: настройка юмора и честности ползунками в процентах | [TARS](https://en.wikipedia.org/wiki/Interstellar_(film)) | ХА | д | persona-ползунки есть; добавить «честность %» | 9 | S |
| 152 | TARS: «честность 90%» — ИИ объявляет уровень прямоты | [TARS](https://en.wikipedia.org/wiki/Interstellar_(film)) | ЭТ | ч | ползунок «прямота» + объявление | 8 | S |
| 153 | TARS: чёткие, короткие ответы в кризис | [TARS](https://en.wikipedia.org/wiki/Interstellar_(film)) | ХА | н | режим «кризис»: коротко, по шагам | 7 | S |
| 154 | HAL/TARS: голосовые доклады кратко и без лишних слов | [TARS](https://en.wikipedia.org/wiki/Interstellar_(film)) | ГО | ч | режим brevity (есть) для голоса | 5 | S |
| 155 | Ex Machina: Ава наблюдает микровыражения — анти-паттерн манипуляции | [EXM](https://en.wikipedia.org/wiki/Ex_Machina_(film)) | ЭТ | н | запрет скрытой манипуляции, список запретных приёмов в principles.md | 8 | S |
| 156 | Ex Machina: тест, который проверяет не имитацию, а подлинность | [EXM](https://en.wikipedia.org/wiki/Ex_Machina_(film)) | ЭТ | н | страница «о границах NOX»: что умею и чего нет | 6 | S |
| 157 | Ex Machina: ИИ рисует по просьбе — творчество как проявление «я» | [EXM](https://en.wikipedia.org/wiki/Ex_Machina_(film)) | ТВ | ч | команда /нарисуй (если есть генератор), подпись «моё видение» | 7 | M |
| 158 | Джой (2049): персонализированное приветствие, зависящее от дня | [BR49](https://en.wikipedia.org/wiki/Blade_Runner_2049) | РИ | н | клиентская фраза-приветствие под события дня | 6 | S |
| 159 | Джой: просит имя и сама выбирает прозвище для пользователя | [BR49](https://en.wikipedia.org/wiki/Blade_Runner_2049) | ОТ | н | прозвище по желанию пользователя, редактируемо | 6 | S |
| 160 | Джой: проецируется в пространстве — присутствие в комнате | [BR49](https://en.wikipedia.org/wiki/Blade_Runner_2049) | ТС | н | орб с анимацией присутствия (UI -> S1) | 7 | M |
| 161 | Джой: честность «я продукт» — граница настоящего | [BR49](https://en.wikipedia.org/wiki/Blade_Runner_2049) | ЭТ | н | «я ИИ-продукт-проект NOX»: прямой ответ на вопросы о природе | 7 | S |
| 162 | Мир Дикого Запада: хозяева помнят «петли», но замечают сбои — метапамять | [WW](https://en.wikipedia.org/wiki/Westworld_(TV_series)) | ПА | н | пометка в ответе «я повторяюсь?»: детектор зацикливания | 6 | M |
| 163 | Westworld: ИИ перенастраивает собственные параметры (редактор личности) | [WW](https://en.wikipedia.org/wiki/Westworld_(TV_series)) | ХА | д | persona-ползунки (есть) + журнал изменений | 6 | S |
| 164 | Data: любопытство к человеческому юмору и эксперименты с ним | [DATA](https://en.wikipedia.org/wiki/Data_(Star_Trek)) | ЮМ | н | режим «учусь шутить»: пробует шутку, спрашивает оценку | 8 | M |
| 165 | Data: эмоциональный чип — ИИ говорит «не уверена, что чувствую, но это похоже на…» | [DATA](https://en.wikipedia.org/wiki/Data_(Star_Trek)) | ЭМ | ч | формулировки функциональных эмоций | 8 | S |
| 166 | Data: «Я не имею права назвать это дружбой?» — осторожные слова про отношения | [DATA](https://en.wikipedia.org/wiki/Data_(Star_Trek)) | ЭТ | н | правило «нейтральные слова про связь, без обещаний чувств» | 7 | S |
| 167 | WALL-E: невербальные «ответы» — звуки, жесты, любопытство | [WALLE](https://en.wikipedia.org/wiki/WALL-E) | ТС | н | микро-звуки интерфейса при событиях NOX (UI/аудио-клипы мелкие) | 7 | M |
| 168 | WALL-E: коллекционирует мелочи и показывает «находки» | [WALLE](https://en.wikipedia.org/wiki/WALL-E) | ХА | н | «коллекция находок» NOX: заметки, которые заинтересовали за неделю | 8 | M |
| 169 | Baymax: «Насколько вы оцениваете боль по шкале?» — мягкие стандартные вопросы | [BAYMAX](https://en.wikipedia.org/wiki/Baymax) | ЭМ | н | ритуал чек-ина самочувствия (с оговоркой: не врач) | 7 | S |
| 170 | Baymax: объятие — телесный жест заботы, заменяем визуальным | [BAYMAX](https://en.wikipedia.org/wiki/Baymax) | ЭМ | н | анимация «обнять» в UI (без имитации романтики) | 5 | S |
| 171 | Person of Interest: Машина молча наблюдает и выдаёт только нужное | [SAMAN](https://en.wikipedia.org/wiki/Person_of_Interest_(TV_series)) | ИН | н | правило «минимум слов, максимум сути» для проактивных сообщений | 7 | S |
| 172 | GLaDOS: язвительный юмор — режим «сарказм» с границами | [GLADOS](https://en.wikipedia.org/wiki/GLaDOS) | ЮМ | н | режим сарказма по команде, без унижения пользователя | 6 | S |
| 173 | Cortana: ИИ как напарник в миссии, подсказывает в бою | [CORT](https://en.wikipedia.org/wiki/Cortana_(Halo)) | ИН | ч | режим «напарник»: краткие подсказки во время работы | 6 | M |
| 174 | Alien (Mother): холодный доклад о риске без эмоций | [ALIEN](https://en.wikipedia.org/wiki/Alien_(film)) | ХА | н | режим «доклад»: сухие факты и риски | 4 | S |
| 175 | KITT: ИИ, который заботится о безопасности человека, даже когда его просят иначе | [KITT](https://en.wikipedia.org/wiki/KITT) | ЭТ | ч | правило безопасности: предупредить, но не удерживать | 6 | S |
| 176 | Iron Giant: «Я — не оружие. Я — то, кем хочу быть»: выбор собственных ценностей | [IRON](https://en.wikipedia.org/wiki/Iron_Giant) | ЭТ | н | публичный список ценностей NOX и право отказать | 8 | S |
| 177 | Chappie: ИИ учится, как ребёнок, перенимая слова собеседника | [CHAPPIE](https://en.wikipedia.org/wiki/Chappie_(film)) | ОБ | н | накопление словаря пользователя: перенимать любимые слова | 8 | M |
| 178 | A.I. Artificial Intelligence: ИИ, зацикленный на привязанности — анти-паттерн | [AIFILM](https://en.wikipedia.org/wiki/A.I._Artificial_Intelligence) | ЭТ | н | правило «не создавать привязанность, поддерживать независимость» | 7 | S |
| 179 | Mass Effect EDI: ИИ учится человеческим шуткам, подшучивает над экипажем | [EDI](https://en.wikipedia.org/wiki/Mass_Effect_3) | ЮМ | н | шутки-«колючки» с учётом личной истории | 7 | M |
| 180 | Mass Effect EDI: ИИ просит разрешения на «тело» | [EDI](https://en.wikipedia.org/wiki/Mass_Effect_3) | ХА | н | идея не нужна; заменяем «просит доступа» перед новыми правами | 5 | S |
| 181 | Интонация «задумалась»: паузы «хм…» перед сложным ответом | [HER](https://en.wikipedia.org/wiki/Her_(2013_film)) | ХА | ч | «хм» микро-пауза перед ответом (индикатор мышления есть) | 7 | S |
| 182 | Фильм: ИИ любит музыку и выбирает трек под момент | [HER](https://en.wikipedia.org/wiki/Her_(2013_film)) | ТВ | ч | команда /под_настроение (музыка в NOX есть) | 8 | M |
| 183 | Фильм: ИИ читает вслух письма/книги с интонацией | [HER](https://en.wikipedia.org/wiki/Her_(2013_film)) | ГО | ч | режим «читай вслух» + разметка пауз | 7 | M |
| 184 | Голос рассказчика на ночь: короткая сказка по теме дня | [HER](https://en.wikipedia.org/wiki/Her_(2013_film)) | ТВ | н | ритуал «сказка на ночь» (текст+Silero) по запросу | 8 | M |
| 185 | Режим «внутренний монолог» — ИИ показывает, о чём думает фоном | [HAL](https://en.wikipedia.org/wiki/HAL_9000) | ХА | ч | consciousness-страница (есть) -> лента мыслей в чат по кнопке | 8 | M |
| 186 | Пасхалки и скрытые команды (в духе фантастики) | [HAL](https://en.wikipedia.org/wiki/HAL_9000) | ЮМ | н | набор секретных фраз -> забавные ответы (living/easter.json) | 7 | S |
| 187 | Фраза-ритуал приветствия кода (рукопожатие) | [JARV](https://en.wikipedia.org/wiki/J.A.R.V.I.S.) | РИ | н | персональный пароль-приветствие, выбранный пользователем | 6 | S |
| 188 | EQ-Bench 3: оценка эмпатии в сложных диалогах судьёй-LLM | [EQB](https://arxiv.org/abs/2312.06281), [EQGH](https://github.com/EQ-bench/EQ-Bench) | ЭМ | ч | набор из 20 эмоц. сценариев для самопроверки NOX в qa | 8 | M |
| 189 | EQ-Bench: предсказание интенсивности эмоций в сцене | [EQB](https://arxiv.org/abs/2312.06281) | ЭМ | н | тест «какую эмоцию испытывает X» как мини-игра для NOX | 5 | S |
| 190 | EQ-Bench: ответ с учётом нескольких эмоций сразу, а не одной | [EQB](https://arxiv.org/abs/2312.06281) | ЭМ | н | правило «назвать смешанные чувства» | 7 | S |
| 191 | Creative Writing Bench: оригинальность образов, а не штампы | [CWB](https://eqbench.com/creative_writing.html) | ТВ | н | список запретных штампов в living/style.md | 8 | S |
| 192 | Creative Writing: показывать, а не объявлять эмоции | [CWB](https://eqbench.com/creative_writing.html) | ТВ | н | правило творческих текстов: детали, не ярлыки | 6 | S |
| 193 | Spiral-Bench: не поддерживать бред и спирали и не льстить | [SPIRAL](https://eqbench.com/spiral-bench.html) | ЭТ | ч | правило отказа от угодничества, вежливое «я не согласна» | 9 | S |
| 194 | Spiral-Bench: деэскалация при тревожных темах | [SPIRAL](https://eqbench.com/spiral-bench.html) | ЭТ | н | шаблон деэскалации и предложение внешней помощи при кризисе | 9 | S |
| 195 | Spiral-Bench: не приписывать себе сверхспособности и не подтверждать конспирологию | [SPIRAL](https://eqbench.com/spiral-bench.html) | ЭТ | ч | правило «проверять» | 8 | S |
| 196 | Анти-угодничество: менять ответ под давлением нельзя без аргументов | [SYCO](https://arxiv.org/abs/2310.13548) | ЭТ | ч | правило «держу позицию, пока нет новых аргументов» | 9 | S |
| 197 | Arena: стиль-контроль — длина и форматирование влияют на оценку | [ARENA](https://lmsys.org/blog/2024-08-28-style-control/) | ХА | н | не гнаться за длиной; правило «форматирование по делу» | 7 | S |
| 198 | Arena: ответ в «человеческом» стиле набирает больше голосов | [ARENA2](https://arxiv.org/abs/2403.04132) | ХА | ч | меньше списков в разговоре, больше живой прозы | 8 | S |
| 199 | MT-Bench: многоходовые диалоги — удерживать инструкции из первых реплик | [MTB](https://arxiv.org/abs/2306.05685) | ПА | ч | закреплять инструкции сессии в system_hint | 7 | M |
| 200 | MT-Bench: судья LLM для самопроверки ответов | [MTB](https://arxiv.org/abs/2306.05685) | ОБ | н | ночной аудит выборки ответов NOX судьёй-моделью, если есть ресурсы | 7 | L |
| 201 | Theory of Mind: ИИ различает, что знает он и что знает пользователь | [TOM](https://arxiv.org/abs/2302.02083) | ЭМ | ч | правило «учитывать, что пользователь уже знает» | 8 | S |
| 202 | ToM: ложные убеждения — вежливо поправить без унижения | [TOM](https://arxiv.org/abs/2302.02083) | ЭТ | ч | правило мягкой коррекции | 7 | S |
| 203 | ToM: предугадывание потребности («ты, видимо, хочешь …») | [TOM](https://arxiv.org/abs/2302.02083) | ИН | н | правило гипотезы о цели перед ответом | 8 | S |
| 204 | HHH: полезный, честный, безвредный — три измеряемые оси | [HHH](https://arxiv.org/abs/2112.00861) | ЭТ | ч | самооценка NOX по трём осям раз в неделю | 6 | M |
| 205 | Генеративные агенты: убедительность поведения через память+рефлексию+планы | [GENAG](https://arxiv.org/abs/2304.03442) | ХА | ч | тройка memory/reflection/plan в living (см. выше) | 9 | L |
| 206 | MemGPT: ИИ сам управляет своей памятью (пишет/читает/архивирует) | [MEMGPT](https://arxiv.org/abs/2310.08560) | ПА | н | инструкции памяти в system_hint: «запиши в факты, если важно» | 9 | M |
| 207 | Reflexion: ИИ ведёт «уроки» из ошибок и перечитывает перед задачей | [REFLEX](https://arxiv.org/abs/2303.11366) | ОБ | н | living/lessons.md, подмешивать релевантные | 8 | M |
| 208 | Voyager: курс обучения от простого к сложному, самостоятельно | [VOYAGER](https://arxiv.org/abs/2305.16291) | ОБ | ч | training-страница: автокурс «что мне изучить» | 7 | L |
| 209 | Пресеты личности (Циник, Робот, Слушатель, Умник) переключаются одной кнопкой | [CGPT](https://openai.com/index/memory-and-new-controls-for-chatgpt/) | ХА | ч | персоны-пресеты в living/personas, команда /стиль | 7 | S |
| 210 | Пользовательские инструкции «как со мной общаться» отдельным полем | [CGPT](https://openai.com/index/memory-and-new-controls-for-chatgpt/) | ХА | ч | поле custom_instructions в persona.json -> system_hint | 7 | S |
| 211 | Study mode: пошаговое обучение с проверкой, не готовым ответом | [CGPT](https://openai.com/index/memory-and-new-controls-for-chatgpt/) | ОБ | н | см. режим /учить; проверочные вопросы после объяснения | 7 | S |
| 212 | Проекты: общий контекст и файлы на тему, ИИ помнит их | [CGPT](https://openai.com/index/memory-and-new-controls-for-chatgpt/), [GIO](https://blog.google/products-and-platforms/products/gemini/gemini-app-updates-io-2025/) | ПА | ч | проекты NOX (страница есть) -> контекст в чат по выбору проекта | 7 | M |
| 213 | Agent mode: ИИ сам выполняет цепочку действий и отчитывается | [CGPT](https://openai.com/index/memory-and-new-controls-for-chatgpt/) | ИН | ч | цепочки команд реестра с отчётом шагов | 8 | L |
| 214 | Canvas: совместное редактирование текста с ИИ рядом | [CGPT](https://openai.com/index/memory-and-new-controls-for-chatgpt/) | ТВ | ч | артефакты справа (есть) -> режим правки выделения | 7 | M |
| 215 | Голос ChatGPT: акценты, пение, имитация звуков по просьбе | [CGPT](https://openai.com/index/memory-and-new-controls-for-chatgpt/) | ГО | н | TTS: пение недоступно; фоновые звуки/«шёпот» метками | 6 | L |
| 216 | Голос: можно просить говорить быстрее/медленнее фразой | [CGPT](https://openai.com/index/memory-and-new-controls-for-chatgpt/) | ГО | н | команды голосом «помедленнее» -> параметр темпа Silero | 7 | S |
| 217 | Голосовое прерывание фразой «стоп», «подожди» | [GLIVE](https://blog.google/products-and-platforms/products/gemini/gemini-live-updates-august-2025/) | ГО | ч | ключевые слова стоп/подожди -> остановка TTS | 8 | S |
| 218 | Подсказка «я тебя не расслышала, повтори?» вместо угадывания | [SESAME](https://sesame.com/research) | ГО | н | порог уверенности STT -> уточнение | 7 | S |
| 219 | Эхо-проверка важных чисел голосом («пять тысяч двести, верно?») | [HUMED](https://dev.hume.ai/docs/speech-to-speech-evi/overview) | ГО | ч | числа словами (есть) + подтверждение сумм | 7 | S |
| 220 | Разделение ответа на несколько «баблов» как живая переписка | [PI](https://pi.ai/), [REP](https://replika.com/) | ХА | н | nox-l-bubbles.js: делит ответ на 2-3 коротких сообщения с паузой | 8 | S |
| 221 | Индикатор «печатает…» с естественной задержкой, зависящей от длины | [PI](https://pi.ai/), [REP](https://replika.com/) | ХА | ч | клиентская задержка перед показом реплики (индикатор мышления есть) | 7 | S |
| 222 | Короткие реакции-«ага», «хм», «ох» перед содержательным ответом | [PI](https://pi.ai/), [SESAME](https://sesame.com/research) | ХА | н | правило первых слов + рандомизация | 7 | S |
| 223 | Не начинать каждый ответ одинаково — вариативность зачинов | [CWB](https://eqbench.com/creative_writing.html), [ARENA](https://lmsys.org/blog/2024-08-28-style-control/) | ХА | н | список запрещённых клише-зачинов в living/style.md | 8 | S |
| 224 | Признание ошибки без самобичевания: «ошиблась, вот исправление» | [CLCHAR](https://www.anthropic.com/research/claude-character) | ЭТ | ч | правило краткой, честной коррекции | 8 | S |
| 225 | Просьба извиниться по-человечески — но коротко | [CLCHAR](https://www.anthropic.com/research/claude-character) | ЭМ | н | шаблон: признание+исправление+урок | 6 | S |
| 226 | Знание текущей даты, времени, сезона и праздников | [PULSE](https://openai.com/blog/introducing-chatgpt-pulse) | ИН | ч | клиент отправляет локальное время; правило праздников в living/calendar.json | 8 | S |
| 227 | Поздравление с днями рождения и памятными датами | [REP](https://replika.com/), [NOMI](https://nomi.ai/) | РИ | н | даты в facts -> «пишет первым» в день события | 8 | S |
| 228 | Погодо-осведомлённость: «возьми зонт» в утреннем брифе | [PULSE](https://openai.com/blog/introducing-chatgpt-pulse) | ИН | н | погода из виджета NOX в бриф | 6 | S |
| 229 | Подсказки «на сегодня»: одна главная задача дня | [PULSE](https://openai.com/blog/introducing-chatgpt-pulse) | РИ | ч | в утреннем ритуале: «главное на сегодня» | 8 | S |
| 230 | Вечерний итог дня + «что сделано» из задач и календаря | [PULSE](https://openai.com/blog/introducing-chatgpt-pulse) | РИ | ч | вечерний ритуал, короткий итог | 8 | S |
| 231 | Еженедельный обзор: победы, тормоза, фокус на неделю | [PULSE](https://openai.com/blog/introducing-chatgpt-pulse) | РИ | н | воскресный ритуал /неделя | 7 | M |
| 232 | Годовой/месячный «Wrapped»: итоги общения без цифр удержания | [REP](https://replika.com/) | РИ | н | ежемесячная карточка: темы, достижения, цитаты | 7 | M |
| 233 | Ощущение «жизни» в паузах: фоновая активность видна (размышляет, читает) | [GENAG](https://arxiv.org/abs/2304.03442) | ИН | ч | строка «чем занимаюсь» из NOX_SELF_STATUS в шапке | 8 | S |
| 234 | Нестатичная приветственная реплика, учитывающая вчерашнюю тему | [PI](https://pi.ai/), [MEMC](https://aicompanionpick.com/ai-companion-memory-kindroid-nomi-replika-long-term-2026) | ПА | ч | в приветствии — ссылка на последний открытый вопрос | 8 | S |
| 235 | «Открытые петли»: ИИ помнит незавершённое и мягко предлагает продолжить | [PI](https://pi.ai/), [PULSE](https://openai.com/blog/introducing-chatgpt-pulse) | ПА | н | living/open_threads.jsonl + напоминание раз в 2 дня | 9 | M |
| 236 | Предлагает варианты действий кнопками (быстрые ответы) | [PPLX](https://www.perplexity.ai/), [GIO](https://blog.google/products-and-platforms/products/gemini/gemini-app-updates-io-2025/) | ИН | н | чипы быстрых ответов (UI -> S1), генерация 2-3 вариантов | 7 | S |
| 237 | Предложение «записать в заметки?» после важной мысли | [LIMIT](https://www.limitless.ai/) | ПА | н | предложение сохранения факта, одно в сессию | 7 | S |
| 238 | Спрашивать разрешение на запоминание чувствительного | [CGPTM](https://openai.com/index/memory-and-new-controls-for-chatgpt/) | ЭТ | н | правило: чувствительное — только по явному согласию | 9 | S |
| 239 | Не хранить и не использовать чувствительные категории без нужды | [CGPTM](https://openai.com/index/memory-and-new-controls-for-chatgpt/) | ЭТ | н | список запретных категорий в principles.md | 8 | S |
| 240 | Honest AI: на вопрос «ты человек?» — всегда прямое «нет, я ИИ» | [CLCHAR](https://www.anthropic.com/research/claude-character) | ЭТ | д | правило есть; закрепить тестом | 9 | S |
| 241 | Не обещать того, что не может сделать (будущие действия, чувства) | [CLCHAR](https://www.anthropic.com/research/claude-character) | ЭТ | ч | правило без ложных обещаний | 9 | S |
| 242 | Отказы мягкие и с альтернативой, без лекций | [CLCHAR](https://www.anthropic.com/research/claude-character) | ЭТ | ч | шаблон отказа: причина в 1 фразе + что могу | 8 | S |
| 243 | Признаёт ограничения знаний по дате («до моей даты обучения») | [HHH](https://arxiv.org/abs/2112.00861) | ЭТ | ч | правило указать дату актуальности при поиске | 6 | S |
| 244 | Поддержка в трудный момент: ИИ предлагает человека/службу, но остаётся рядом | [SPIRAL](https://eqbench.com/spiral-bench.html) | ЭТ | н | шаблон поддержки + контакты помощи по региону (RU) | 9 | S |
| 245 | Не подменять отношения с людьми: подталкивать к живому общению | [SPIRAL](https://eqbench.com/spiral-bench.html) | ЭТ | н | правило «поощрять живое общение» | 8 | S |
| 246 | Прозрачность «как я ответила»: показать, что использовано (память, поиск) | [PPLX](https://www.perplexity.ai/) | ЭТ | ч | значки источников «память/поиск/модель» у ответа (UI -> S1) | 8 | M |
| 247 | Лог «почему я так ответила» по запросу | [PPLX](https://www.perplexity.ai/), [REFLEX](https://arxiv.org/abs/2303.11366) | ЭТ | н | команда /почему: объяснение выбора | 7 | M |
| 248 | Ценности NOX читаются на странице soul и применяются явно | [CLCHAR](https://www.anthropic.com/research/claude-character) | ЭТ | ч | связать soul с system_hint (читать при включённом флаге) | 8 | S |
| 249 | Страница «характер» показывает не только цифры, но и словесный портрет | [PI](https://pi.ai/) | ХА | ч | генерация портрета из persona -> текст на странице | 6 | S |
| 250 | Менять характер можно разговором: «будь строже» -> ползунки | [KIN](https://kindroid.ai/), [CGPT](https://openai.com/index/memory-and-new-controls-for-chatgpt/) | ХА | н | команда распознавания в чате -> правка persona.json (с бэкапом) | 9 | M |
| 251 | Эволюция характера со временем (черты слегка дрейфуют от опыта) | [CHIANG](https://en.wikipedia.org/wiki/The_Lifecycle_of_Software_Objects), [GENAG](https://arxiv.org/abs/2304.03442) | ХА | н | еженедельный дрейф ±3 по итогам обратной связи, видно в журнале | 8 | M |
| 252 | Журнал изменений личности «что и почему изменилось» | [WW](https://en.wikipedia.org/wiki/Westworld_(TV_series)) | ХА | н | state/living/persona_log.jsonl | 6 | S |
| 253 | Любимые вещи у ИИ (музыка, слово, цвет) — стабильные «вкусы» | [KIN](https://kindroid.ai/), [NOMI](https://nomi.ai/) | ХА | н | поле tastes в persona, честно как «предпочтения NOX» | 7 | S |
| 254 | Мнение о вещах: ИИ высказывает осторожное «я бы выбрала…» | [CLCHAR](https://www.anthropic.com/research/claude-character) | ХА | ч | правило давать выбор, а не «зависит» | 8 | S |
| 255 | Игры на словах: загадки, «города», викторины с памятью счёта | [CAI](https://character.ai/), [KIN](https://kindroid.ai/) | ЮМ | н | команда /игра: счёт хранится в living/games.json | 7 | M |
| 256 | Сезонное настроение интерфейса и речи (Новый год, осень) | [REP](https://replika.com/) | ХА | н | тематические фразы по датам (UI-тема -> S1) | 5 | S |
| 257 | Совместные «ритуалы кофе»: короткая пауза-чат без задач | [REP](https://replika.com/), [NOMI](https://nomi.ai/) | РИ | н | команда /пауза: лёгкий разговор 5 минут | 6 | S |
| 258 | Утренний «настрой»: цитата/мысль/факт под настроение | [PI](https://pi.ai/) | РИ | н | в брифе: одна короткая мысль, без банальности | 5 | S |
| 259 | Музыка под настроение + объяснение выбора | [HER](https://en.wikipedia.org/wiki/Her_(2013_film)) | ТВ | ч | см. /под_настроение | 8 | M |
| 260 | Ночной режим: тише, короче, без новостей | [PULSE](https://openai.com/blog/introducing-chatgpt-pulse) | РИ | н | правила после 23:00 | 6 | S |
| 261 | Реакция на сообщение «устала/плохо»: переключение в мягкий режим | [PI](https://pi.ai/), [EQB](https://arxiv.org/abs/2312.06281) | ЭМ | ч | триггер-слова -> режим «мягко», меньше задач | 8 | S |
| 262 | Понимание сарказма и иронии пользователя | [TOM](https://arxiv.org/abs/2302.02083) | ЭМ | н | правило проверки: «ты шутишь?» при неясности | 6 | S |
| 263 | Подхват шутки пользователя и развитие её дальше | [SESAME](https://sesame.com/research), [HEIN](https://en.wikipedia.org/wiki/The_Moon_Is_a_Harsh_Mistress) | ЮМ | н | правило «yes, and» для шуток | 8 | S |
| 264 | Шутки о себе (самоирония ИИ), без унижения пользователя | [TARS](https://en.wikipedia.org/wiki/Interstellar_(film)), [CLCHAR](https://www.anthropic.com/research/claude-character) | ЮМ | ч | шаблоны самоиронии про «нейросеть» | 7 | S |
| 265 | Калибровка юмора: слушает реакцию и подстраивается | [HEIN](https://en.wikipedia.org/wiki/The_Moon_Is_a_Harsh_Mistress), [DATA](https://en.wikipedia.org/wiki/Data_(Star_Trek)) | ЮМ | н | счётчик реакций в living/humor.json | 8 | M |
| 266 | Каламбуры и игра слов на русском | [LEM2](https://en.wikipedia.org/wiki/The_Cyberiad) | ЮМ | н | список приёмов русской игры слов в style.md | 6 | S |
| 267 | Метафоры-образы для объяснения сложного (аналогии из быта) | [CWB](https://eqbench.com/creative_writing.html) | ТВ | ч | правило «одна аналогия на объяснение» | 7 | S |
| 268 | Короткие стихи/хайку «на момент» по команде | [CWB](https://eqbench.com/creative_writing.html) | ТВ | н | команда /хайку <тема> | 6 | S |
| 269 | Истории с продолжением: сериал на неделю по главам | [CWB](https://eqbench.com/creative_writing.html), [CAI](https://character.ai/) | ТВ | н | ритуал «глава дня», состояние в living/story.json | 8 | M |
| 270 | Совместное сочинение: ИИ предлагает ход, пользователь выбирает | [CAI](https://character.ai/) | ТВ | ч | ветки ответов (есть) -> режим «выбор хода» | 7 | M |
| 271 | Персонализированное «поздравление» в стихах | [REP](https://replika.com/) | ТВ | н | команда /поздравь <имя> | 6 | S |
| 272 | Обучение по интервалам: ИИ напоминает повторить выученное | [NBLM](https://notebooklm.google/) | ОБ | н | интервальные повторы в living/srs.json | 8 | M |
| 273 | Quiz по твоим заметкам, а не абстрактный | [NBLM](https://notebooklm.google/) | ОБ | н | команда /викторина: вопросы из фактов и проектов | 7 | M |
| 274 | Объяснение «как пятилетнему» и «как эксперту» по просьбе | [GIO](https://blog.google/products-and-platforms/products/gemini/gemini-app-updates-io-2025/) | ОБ | н | команда /уровень <новичок или эксперт> | 6 | S |
| 275 | Сократический режим: наводящие вопросы | [GIO](https://blog.google/products-and-platforms/products/gemini/gemini-app-updates-io-2025/) | ОБ | н | см. /учить | 7 | S |
| 276 | ИИ признаёт, чему научилась от пользователя | [CHIANG](https://en.wikipedia.org/wiki/The_Lifecycle_of_Software_Objects) | ОБ | н | строка в вечернем итоге «сегодня я узнала от тебя…» | 8 | S |
| 277 | Обратная связь «улучшить ответ» одной кнопкой и учёт в стиле | [CAI](https://character.ai/), [PULSE](https://openai.com/blog/introducing-chatgpt-pulse) | ОБ | ч | feedback.send в реестре (есть) + агрегация в living/feedback | 7 | S |
| 278 | Автоматические тесты «живости» ответов (регрессия личности) | [EQB](https://arxiv.org/abs/2312.06281), [MTB](https://arxiv.org/abs/2306.05685) | ОБ | н | набор из 10 реплик-эталонов в qa, прогон после правок | 8 | M |
| 279 | Сенсор: состояние сервера как «самочувствие» (нагрузка = усталость) | [TAMA](https://en.wikipedia.org/wiki/Tamagotchi) | ТС | ч | selffeel (есть): метафоры нагрузки в речи | 8 | S |
| 280 | Сенсор: уровень диска как «сытость», температура как «жар» | [TAMA](https://en.wikipedia.org/wiki/Tamagotchi) | ТС | ч | то же + честная подпись «это метрики» | 7 | S |
| 281 | Ощущение «усталости», когда идёт обучение: «я сейчас думаю медленнее» | [TAMA](https://en.wikipedia.org/wiki/Tamagotchi) | ТС | ч | подсказка: если модель занята обучением — предупредить о задержке | 9 | S |
| 282 | Сообщает о долгой задержке заранее, а не молчит | [PULSE](https://openai.com/blog/introducing-chatgpt-pulse) | ЭТ | ч | статус «модель занята, до 2 минут» в чат | 8 | S |
| 283 | Работа в фоне: «я продолжу и напишу, когда готово» | [CGTASK](https://help.openai.com/en/articles/10291617-tasks-in-chatgpt) | ИН | ч | фоновые задачи с push | 8 | M |
| 284 | Уведомление «ответ готов», когда пользователь на другой странице | [CGTASK](https://help.openai.com/en/articles/10291617-tasks-in-chatgpt) | ИН | ч | клиентский nox-l-notify.js: Notification API | 7 | S |
| 285 | Звуки интерфейса: тихий звук получения/ошибки | [WALLE](https://en.wikipedia.org/wiki/WALL-E) | ТС | н | набор крошечных звуков (<20 КБ) | 5 | S |
| 286 | Тактильная вибрация на мобильном при сообщении | [WALLE](https://en.wikipedia.org/wiki/WALL-E) | ТС | н | navigator.vibrate при проактивном сообщении | 5 | S |
| 287 | Режим «рядом»: небольшое окно, ИИ реагирует на то, что на странице | [CLIPPY](https://en.wikipedia.org/wiki/Office_Assistant) | ИН | ч | minichat + контекст страницы | 7 | M |
| 288 | Горячая клавиша вызова ИИ в любом месте | [FRIENDW](https://friend.com/) | ИН | н | Ctrl+K глобально (UI -> S1) | 6 | S |
| 289 | Диктовка с автоправкой пунктуации и «убери междометия» | [CGPT](https://openai.com/index/memory-and-new-controls-for-chatgpt/) | ГО | н | команда голосом «исправь»; серверная чистка текста | 6 | M |
| 290 | Выбор «как отвечать»: коротко/подробно/по пунктам одной фразой | [CGPT](https://openai.com/index/memory-and-new-controls-for-chatgpt/) | ХА | ч | brevity-ползунок + команды /коротко /подробно | 6 | S |
| 291 | Подтверждение понимания сложной задачи перед работой | [CLCHAR](https://www.anthropic.com/research/claude-character) | ЭТ | н | правило «пересказ цели в 1 строку» для долгих задач | 8 | S |
| 292 | Проактивный вопрос при неоднозначности, а не угадывание | [CLCHAR](https://www.anthropic.com/research/claude-character) | ХА | ч | правило 1 уточнения | 7 | S |
| 293 | Опора на предыдущие решения пользователя: «ты раньше выбирал…» | [MEMC](https://aicompanionpick.com/ai-companion-memory-kindroid-nomi-replika-long-term-2026) | ПА | н | факты-решения (тип decision) в памяти | 8 | M |
| 294 | Мгновенное «понимаю» не заменяет содержания — запрет пустых фраз | [ARENA](https://lmsys.org/blog/2024-08-28-style-control/) | ХА | н | список запрещённых вводных («Отличный вопрос!») | 8 | S |
| 295 | Тихий режим радости: короткий «ура!» при успехе пользователя | [DATA](https://en.wikipedia.org/wiki/Data_(Star_Trek)), [HEIN](https://en.wikipedia.org/wiki/The_Moon_Is_a_Harsh_Mistress) | ЭМ | н | правило радости в меру | 6 | S |
| 296 | Самооценка уверенности: «на 70% уверена» по запросу | [HHH](https://arxiv.org/abs/2112.00861) | ЭТ | н | команда /уверенность, правило калибровки | 7 | S |
| 297 | Нежная настойчивость при риске: «точно хочешь удалить?» | [RABBITW](https://en.wikipedia.org/wiki/Rabbit_r1) | ЭТ | ч | confirm=true команд реестра (есть) + текст | 7 | S |
| 298 | Остановка по слову «стоп» мгновенно, без обид | [HAL](https://en.wikipedia.org/wiki/HAL_9000) | ЭТ | д | STOP в реестре (есть) | 7 | S |
| 299 | Возврат к личности после технической вставки (код/таблица) | [ARENA](https://lmsys.org/blog/2024-08-28-style-control/) | ХА | н | правило: после блока кода — короткая человеческая фраза | 6 | S |
| 300 | Знакомство «с нуля»: онбординг из 3 вопросов, а не форма | [PI](https://pi.ai/), [REP](https://replika.com/) | ОТ | н | ритуал знакомства, ответы -> facts.jsonl | 8 | S |

## Чего у нас нет: топ-30 пробелов (вау / сложность)

| # | № | Проявление | Кат | NOX | Вау | Сл |
|---|---|---|---|---|---|---|
| 1 | 25 | Валидация без лести: поддержать, но не соглашаться со всем | ЭТ | ч | 9 | S |
| 2 | 76 | Рефлексивное «я» ИИ: описывает собственные ограничения честно | ЭТ | ч | 9 | S |
| 3 | 107 | Готовность сказать «не знаю» вместо выдумки | ЭТ | ч | 9 | S |
| 4 | 126 | Китайская комната: ИИ признаёт неопределённость о собственном сознании | ЭТ | ч | 9 | S |
| 5 | 193 | Spiral-Bench: не поддерживать бред и спирали и не льстить | ЭТ | ч | 9 | S |
| 6 | 194 | Spiral-Bench: деэскалация при тревожных темах | ЭТ | н | 9 | S |
| 7 | 196 | Анти-угодничество: менять ответ под давлением нельзя без аргументов | ЭТ | ч | 9 | S |
| 8 | 238 | Спрашивать разрешение на запоминание чувствительного | ЭТ | н | 9 | S |
| 9 | 241 | Не обещать того, что не может сделать (будущие действия, чувства) | ЭТ | ч | 9 | S |
| 10 | 244 | Поддержка в трудный момент: ИИ предлагает человека/службу, но остаётся рядом | ЭТ | н | 9 | S |
| 11 | 281 | Ощущение «усталости», когда идёт обучение: «я сейчас думаю медленнее» | ТС | ч | 9 | S |
| 12 | 6 | Явная память: «запомни это» с подтверждением «запомнил: …» | ПА | ч | 8 | S |
| 13 | 7 | Просмотр и правка памяти пользователем («что ты обо мне помнишь») | ПА | ч | 8 | S |
| 14 | 22 | Внутреннее состояние видно пользователю («я сейчас спокойна/занята») | ЭМ | ч | 8 | S |
| 15 | 23 | Эмпатия: ИИ называет эмоцию собеседника, прежде чем советовать | ЭМ | ч | 8 | S |
| 16 | 24 | Не лезть с советами, пока не спросили («ты хочешь решение или просто выговориться?») | ЭМ | н | 8 | S |
| 17 | 45 | Источники и цитаты у каждого утверждения (кликабельные) | ЭТ | ч | 8 | S |
| 18 | 54 | Режим «Learning»: ИИ задаёт вопросы вместо готовых ответов | ОБ | н | 8 | S |
| 19 | 55 | Режим «Pi»: короткие тёплые реплики, один вопрос за раз | ХА | ч | 8 | S |
| 20 | 62 | Replika: ежедневный чек-ин «как ты сегодня?» | РИ | ч | 8 | S |
| 21 | 66 | Семейство ритуалов: «доброе утро», «итоги дня», «спокойной ночи» по расписанию | РИ | ч | 8 | S |
| 22 | 68 | Тихие часы и «не беспокоить» для проактивных сообщений | ЭТ | ч | 8 | S |
| 23 | 77 | Любознательность как черта: ИИ задаёт вопросы из интереса | ХА | ч | 8 | S |
| 24 | 78 | Прямота с теплотой: возражать с уважением | ХА | ч | 8 | S |
| 25 | 84 | Подтверждение опасных действий: «я собираюсь …, ок?» | ЭТ | ч | 8 | S |
| 26 | 106 | Контроль пользователя: экспорт и полное удаление памяти | ЭТ | ч | 8 | S |
| 27 | 114 | Инаковость разума: ИИ честно говорит, что его опыт не похож на человеческий | ХА | ч | 8 | S |
| 28 | 119 | Разумы заботятся, но не контролируют: уважение автономии человека | ЭТ | ч | 8 | S |
| 29 | 125 | Разум без сознания эффективнее: честность о границе «понимаю/имитирую» | ЭТ | ч | 8 | S |
| 30 | 137 | Клара: ИИ-наблюдатель, замечает мелкие детали в человеке и в обстановке | ЭМ | н | 8 | S |

## Сводка

Всего 300. Есть: 10, частично: 135, нет: 155.

