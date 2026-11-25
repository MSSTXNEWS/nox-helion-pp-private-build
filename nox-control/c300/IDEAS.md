# NOX HELION: идеи для дизайнеров (креативщик K, 25.11.2026)

Только идеи, кода нет. Всё на готовых open-source модулях, без платных API, без Docker, без пиратских сервисов.
Правило владельца: у каждой идеи есть конкретный npm-пакет или репозиторий с лицензией (реестр в конце файла, лицензии сверены через `npm view`). Идеи без движка заменены.

## Как читать
- Сл.: S (до дня, один модуль), M (несколько дней, интеграция с данными ядра), L (неделя и больше).
- Вау: 1-10, моя оценка.
- Лицензии сверены через npm view (см. реестр). Перед установкой всё равно открыть LICENSE.
- Ссылки. Проверены поиском или чтением: Raycast v2 https://manual.raycast.com/new-in-v2 ; Raycast changelog https://www.raycast.com/changelog ; visionOS https://developer.apple.com/wwdc25/guides/visionos/ ; MediaPipe https://developers.google.com/edge/mediapipe/solutions/vision/gesture_recognizer/web_js ; hand-tracking на three.js https://github.com/collidingScopes/threejs-handtracking-101 (MIT) ; Krea https://www.krea.ai/news/product ; Paper Shaders https://shaders.paper.design ; Linear command menu https://linear.app/changelog/2019-12-18-new-command-menu ; Awwwards https://www.awwwards.com/websites/. Остальные ссылки ведут на главные страницы сервисов или репозиториев (глубокие страницы не проверял).
- Исключено сознательно: tldraw (лицензия не свободна для продакшена), Spline, @imgly/background-removal и audioMotion-analyzer (AGPL), любые платные API (ElevenLabs, Midjourney, Runway API). Их приёмы взяты как идеи, движки заменены локальными.
- Документы с Google Диска (канон v6.1, реестр задач) найдены, но не вычитывал целиком: задача только про идеи. Сверку с каноном сделать при отборе.
- Разделов 30 (диспетчер отделён от системы). Страницы «мозга»: сознание, организм, душа, рост, самоощущение.

## 1. Чат
| # | Идея (где подсмотрено) | Модуль, лицензия | ИИ-команда / данные | Вау | Сл. |
|---|---|---|---|---|---|
| 1.1 | Ветвление беседы и авто-сводка длинных чатов (Raycast AI Chat, manual.raycast.com/new-in-v2) | @xyflow/react MIT (карта веток), react-markdown MIT | «ветка от сообщения N», данные: дерево ходов из ядра | 7 | M |
| 1.2 | Плавное проявление токенов по словам (ChatGPT, Claude) | Motion (motion.dev) MIT | поток SSE-токенов | 6 | S |
| 1.3 | Аура вокруг поля ввода, цвет и пульс от состояния ИИ (ожидание, думает, отвечает) | ogl Unlicense | статусы хода из API | 8 | M |
| 1.4 | «Покажи ИИ экран»: снимок текущего раздела уходит в чат (Raycast Screen Awareness) | html-to-image MIT | «посмотри на этот раздел», данные: снимок DOM | 7 | S |
| 1.5 | Артефакты в боковой панели (Claude artifacts, claude.ai) | CodeMirror 6 MIT, iframe sandbox | «открой результат справа», данные: код/HTML ответа | 7 | M |

## 2. Главная
| # | Идея | Модуль, лицензия | ИИ-команда / данные | Вау | Сл. |
|---|---|---|---|---|---|
| 2.1 | Bento-мозаика живых виджетов (Apple, Linear) | GridStack MIT | «добавь виджет X», данные: состояние служб | 6 | S |
| 2.2 | Солнце сцены дышит от нагрузки и речи ИИ | three.js MIT | метрики GPU/ответа | 8 | M |
| 2.3 | Утренний бриф карточками-историями | Embla Carousel MIT | «что нового», данные: календарь, новости, задачи | 6 | S |
| 2.4 | Liquid-glass панели (visionOS 26 / iOS 26, developer.apple.com/wwdc25) через SVG feDisplacementMap + backdrop-filter | liquid-glass-react MIT | оформление, данных нет | 9 | S |

## 3. Кинотеатр
| # | Идея | Модуль, лицензия | ИИ-команда / данные | Вау | Сл. |
|---|---|---|---|---|---|
| 3.1 | Ambilight: фон светится цветами кадра (Philips, Apple TV) | fast-average-color MIT, canvas | «включи подсветку», данные: кадры видео | 9 | S |
| 3.2 | Экран в 3D-зале, отражение на полу (visionOS Cinema) | three.js VideoTexture MIT | «кино-режим» | 9 | M |
| 3.3 | Плеер с превью-кадрами на таймлайне и субтитрами | vidstack MIT, hls.js Apache-2.0 | «найди момент про X» | 5 | S |
| 3.4 | Поиск по реплике: локальный транскрипт и переход к моменту (Netflix, YouTube Chapters) | transformers.js Apache-2.0 (Whisper) | «перемотай на где сказали X», данные: транскрипт | 7 | L |

Только свои и легальные файлы.

## 4. Музыка
| # | Идея | Модуль, лицензия | ИИ-команда / данные | Вау | Сл. |
|---|---|---|---|---|---|
| 4.1 | MilkDrop-визуализатор фоном сцены | butterchurn MIT | «визуализация вкл», данные: аудио-поток | 9 | S |
| 4.2 | Синхро-текст с подсветкой слов (Apple Music, Spotify) | lrc-kit MIT, meyda MIT (бит) | данные: LRC, ритм | 7 | S |
| 4.3 | Волна и спектрограмма с регионами | wavesurfer.js BSD-3 | «вырежи фрагмент» | 6 | S |
| 4.4 | Планеты сцены = частотные полосы, орбиты качаются от баса | tone MIT (Tone.Analyser), three MIT | данные: FFT | 9 | M |

## 5. Новости
| # | Идея | Модуль, лицензия | ИИ-команда / данные | Вау | Сл. |
|---|---|---|---|---|---|
| 5.1 | Лента облаком карточек вокруг камеры (Awwwards-приём) | three.js CSS3DRenderer MIT | «покажи новости про X» | 7 | M |
| 5.2 | Сводка со сносками-источниками (Perplexity) | rss-parser MIT, @mozilla/readability Apache-2.0 | «сводка за день», данные: RSS | 6 | S |
| 5.3 | События на вращающемся глобусе | cobe MIT | координаты новостей | 8 | S |
| 5.4 | Озвученный выпуск локально | kokoro-js Apache-2.0 | «зачитай выпуск» | 7 | M |

## 6. Фото
| # | Идея | Модуль, лицензия | ИИ-команда / данные | Вау | Сл. |
|---|---|---|---|---|---|
| 6.1 | Фото оживает: 2.5D-параллакс по карте глубины (Apple Spatial Scenes, visionOS 26) | transformers.js Apache-2.0 (Depth Anything V2 Small, проверить лицензию весов), three.js | «сделай объёмным» | 9 | M |
| 6.2 | Слайдер до/после | img-comparison-slider MIT | сравнение версий | 5 | S |
| 6.3 | Поиск по смыслу («закат у моря») | transformers.js CLIP Apache-2.0, Orama Apache-2.0 | «найди фото где X» | 8 | M |
| 6.4 | WebGL-фильтры живым превью | PixiJS MIT, pixi-filters MIT | «сделай теплее» | 6 | S |

## 7. Студия
| # | Идея | Модуль, лицензия | ИИ-команда / данные | Вау | Сл. |
|---|---|---|---|---|---|
| 7.1 | Рисуешь штрихом, картинка рождается рядом в реальном времени (Krea Realtime, krea.ai/news/product) | Konva MIT, локальный генератор из каталога imagegen/ComfyUI GPL-3 без Docker | «дорисуй по наброску» | 9 | L |
| 7.2 | Граф-пайплайн генерации из узлов (Krea nodes, ComfyUI) | @xyflow/react MIT | запуск графа | 8 | M |
| 7.3 | Сетка 2x2 вариантов и «ещё такие» (Midjourney) | Motion MIT | «вариации» | 6 | S |

## 8. Дизайн
| # | Идея | Модуль, лицензия | ИИ-команда / данные | Вау | Сл. |
|---|---|---|---|---|---|
| 8.1 | Живые токены темы: ИИ крутит палитру и стекло голосом | Tweakpane MIT, Style Dictionary Apache-2.0 | «сделай холоднее», токены CSS | 7 | S |
| 8.2 | Палитра из обоев/фото в OKLCH | colorjs.io MIT | «подбери цвета из фото» | 6 | S |
| 8.3 | Курсор ИИ рисует на макете как коллега в Figma (figma.com multiplayer) | Excalidraw MIT + Yjs MIT | «нарисуй схему» | 9 | M |

## 9. Голос
| # | Идея | Модуль, лицензия | ИИ-команда / данные | Вау | Сл. |
|---|---|---|---|---|---|
| 9.1 | Фон сцены дышит от голоса (см. F1) | tone MIT (Analyser), ogl Unlicense | амплитуда микрофона/TTS | 9 | S |
| 9.2 | Говори без кнопки и перебивай ИИ (ChatGPT voice) | @ricky0123/vad-web MIT (Silero) | старт/стоп хода, STOP | 8 | M |
| 9.3 | Локальные STT и TTS | transformers.js Whisper Apache-2.0, kokoro-js Apache-2.0 | реплики, голос ответа | 7 | M |
| 9.4 | Голосовой орб: шейдер-сфера, амплитуда = форма (ChatGPT, Gemini Live) | ogl Unlicense | уровень звука | 9 | S |

## 10. Доска
| # | Идея | Модуль, лицензия | ИИ-команда / данные | Вау | Сл. |
|---|---|---|---|---|---|
| 10.1 | ИИ рисует схему по описанию | Excalidraw MIT, @excalidraw/mermaid-to-excalidraw MIT | «нарисуй схему архитектуры» | 8 | M |
| 10.2 | Совместная доска с телефона и проектора | Yjs MIT, y-webrtc | синхронизация | 7 | M |
| 10.3 | Перетащить карточку памяти на доску стикером | dnd-kit MIT | связь с разделом памяти | 5 | S |

## 11. Проекты
| # | Идея | Модуль, лицензия | ИИ-команда / данные | Вау | Сл. |
|---|---|---|---|---|---|
| 11.1 | Клавиши как в Linear (C создать, J/K листать, linear.app) | tinykeys MIT | «создай задачу» | 6 | S |
| 11.2 | Gantt | Frappe Gantt MIT | сроки задач | 5 | S |
| 11.3 | Граф зависимостей, ИИ подсвечивает критический путь | @xyflow/react MIT, dagre MIT | «что блокирует X» | 7 | M |
| 11.4 | Кольца прогресса циклов | d3-shape ISC | прогресс проектов | 5 | S |

## 12. Календарь
| # | Идея | Модуль, лицензия | ИИ-команда / данные | Вау | Сл. |
|---|---|---|---|---|---|
| 12.1 | Сетка с ИИ-блоками времени | Schedule-X MIT | «найди окно на 2 часа» | 6 | M |
| 12.2 | События как планеты на орбитах недели | d3 ISC, three.js MIT | события календаря | 8 | M |
| 12.3 | Ввод фразой («завтра в 10 созвон») | chrono-node MIT | создание события | 6 | S |
| 12.4 | Небо за окном по времени суток | suncalc BSD-2 | время и координаты | 7 | S |

## 13. Память
| # | Идея | Модуль, лицензия | ИИ-команда / данные | Вау | Сл. |
|---|---|---|---|---|---|
| 13.1 | 3D-граф знаний, полёт камеры к узлу (Obsidian graph) | 3d-force-graph MIT | «покажи связи X», данные: записи памяти | 9 | S |
| 13.2 | Семантический поиск | Orama Apache-2.0, transformers.js эмбеддинги | «вспомни про X» | 7 | M |
| 13.3 | Лента жизни с зумом | vis-timeline Apache-2.0/MIT | события памяти по датам | 6 | S |
| 13.4 | Вики-ссылки [[...]] и обратные ссылки (Obsidian) | markdown-it MIT | связи записей | 6 | S |

## 14. Обучение
| # | Идея | Модуль, лицензия | ИИ-команда / данные | Вау | Сл. |
|---|---|---|---|---|---|
| 14.1 | Интервальные повторения для карточек | ts-fsrs MIT | «повтори» | 6 | S |
| 14.2 | Живая кривая loss и «нейрограф» обучения | uPlot MIT | метрики обучения | 7 | S |
| 14.3 | Дерево навыков как в играх | @xyflow/react MIT | освоенные навыки | 7 | M |

## 15. Система
| # | Идея | Модуль, лицензия | ИИ-команда / данные | Вау | Сл. |
|---|---|---|---|---|---|
| 15.1 | Панели как в Grafana (grafana.com), перетаскиваемые | uPlot MIT, GridStack MIT | метрики сервера | 6 | S |
| 15.2 | Радиальные HUD-кольца GPU/RAM/диск | d3-shape ISC | нагрузка | 7 | S |
| 15.3 | Окно живых логов | xterm.js MIT | tail логов | 6 | S |
| 15.4 | Тревога: фон краснеет пульсом | sonner MIT | алерты | 6 | S |

## 16. Диспетчер
| # | Идея | Модуль, лицензия | ИИ-команда / данные | Вау | Сл. |
|---|---|---|---|---|---|
| 16.1 | Очередь задач как карта-метро | @xyflow/react MIT, dagre | очередь и исполнители | 7 | M |
| 16.2 | STOP удержанием, как в HUD (кольцо заполняется) | motion MIT (жест удержания) | отмена хода по request_id | 6 | S |
| 16.3 | Частицы бегут по рёбрам между агентами | @xyflow/react animated edges | потоки задач | 8 | M |

## 17. Сознание
| # | Идея | Модуль, лицензия | ИИ-команда / данные | Вау | Сл. |
|---|---|---|---|---|---|
| 17.1 | Поток мыслей: GPU-частицы, плотность от активности | three.js GPUComputationRenderer MIT | активность ядра | 9 | M |
| 17.2 | Нейрограф активаций | Cytoscape.js MIT | модули в работе | 7 | M |
| 17.3 | Внутренний монолог бегущей строкой с глитчем | typewriter-effect MIT | журнал рефлексии | 6 | S |

## 18. Организм
| # | Идея | Модуль, лицензия | ИИ-команда / данные | Вау | Сл. |
|---|---|---|---|---|---|
| 18.1 | 25 компонентов как органы на схеме | motion MIT | здоровье компонентов | 7 | M |
| 18.2 | Сердцебиение звуком и светом в такт нагрузке | Tone.js MIT | пульс = нагрузка | 8 | S |
| 18.3 | Клетки и капилляры (instanced mesh, шум) | three.js MIT, simplex-noise MIT | потоки данных | 8 | M |

## 19. Душа
| # | Идея | Модуль, лицензия | ИИ-команда / данные | Вау | Сл. |
|---|---|---|---|---|---|
| 19.1 | Жидкая капля-эмоция (метаболлы-шейдер) | @paper-design/shaders Apache-2.0 | эмоциональное состояние | 9 | S |
| 19.2 | Колесо эмоций Плутчика | d3 ISC | текущая смесь эмоций | 6 | S |
| 19.3 | Нейрохимия созвездием звёзд | tsparticles MIT | уровни гормонов | 7 | S |

## 20. Рост
| # | Идея | Модуль, лицензия | ИИ-команда / данные | Вау | Сл. |
|---|---|---|---|---|---|
| 20.1 | Дерево растёт из L-системы по метрикам | lindenmayer MIT, three.js | прогресс обучения | 8 | M |
| 20.2 | Анимация смены стадий | Rive runtime MIT | стадия развития | 7 | M |
| 20.3 | Новый уровень: конфетти и звук | canvas-confetti ISC | событие уровня | 5 | S |

## 21. Самоощущение
| # | Идея | Модуль, лицензия | ИИ-команда / данные | Вау | Сл. |
|---|---|---|---|---|---|
| 21.1 | Радар ощущений (сенсориум) | Apache ECharts Apache-2.0 | значения ощущений | 6 | S |
| 21.2 | Силуэт тела с тепловыми зонами | d3 ISC | нагрузка по узлам | 7 | M |
| 21.3 | Ощущение = лёгкая вибрация и звук | howler MIT (звук ощущений) | события ощущений | 7 | S |

## 22. Атлас
| # | Идея | Модуль, лицензия | ИИ-команда / данные | Вау | Сл. |
|---|---|---|---|---|---|
| 22.1 | Глобус-карта с офлайн-тайлами | MapLibre GL BSD-3, PMTiles BSD-3 | «покажи место X» | 8 | M |
| 22.2 | Дуги связей на 3D-глобусе | globe.gl MIT | связи/маршруты | 8 | S |
| 22.3 | Звёздное небо, созвездия | d3-celestial BSD-3 | координаты | 8 | M |

## 23. Финансы
| # | Идея | Модуль, лицензия | ИИ-команда / данные | Вау | Сл. |
|---|---|---|---|---|---|
| 23.1 | Свечные и линейные графики | lightweight-charts Apache-2.0 (нужна атрибуция) | котировки/траты | 6 | S |
| 23.2 | Sankey потоков денег | d3-sankey BSD-3 | доходы и расходы | 7 | S |
| 23.3 | Категории как планеты по размеру | three.js MIT | суммы по категориям | 7 | M |
| 23.4 | Вопрос словами («сколько на еду») | Orama Apache-2.0 | запрос к данным | 6 | M |

## 24. PDF
| # | Идея | Модуль, лицензия | ИИ-команда / данные | Вау | Сл. |
|---|---|---|---|---|---|
| 24.1 | Выдели абзац и спроси ИИ | pdf.js Apache-2.0 | «объясни выделенное» | 6 | M |
| 24.2 | OCR сканов | tesseract.js Apache-2.0 | «распознай» | 5 | S |
| 24.3 | Листание страниц 3D-переворотом | StPageFlip MIT | навигация | 8 | S |
| 24.4 | Слить, подписать, разрезать | pdf-lib MIT | операции над файлом | 5 | S |

## 25. Загрузки
| # | Идея | Модуль, лицензия | ИИ-команда / данные | Вау | Сл. |
|---|---|---|---|---|---|
| 25.1 | Drag-and-drop с кольцом прогресса | Uppy MIT | статус загрузки | 5 | S |
| 25.2 | Файл втягивается в «чёрную дыру» сцены | three.js MIT | событие drop | 8 | M |
| 25.3 | Авто-метки типов и ИИ-описание | file-type MIT | «разложи загрузки» | 5 | S |

## 26. Настройки
| # | Идея | Модуль, лицензия | ИИ-команда / данные | Вау | Сл. |
|---|---|---|---|---|---|
| 26.1 | Поиск по настройкам (Raycast v2) | Fuse.js Apache-2.0 | «где настройка X» | 6 | S |
| 26.2 | Живое превью темы при движении ползунка | Tweakpane MIT | значения темы | 6 | S |
| 26.3 | Профиль владельца и редактор того, что ИИ запомнил (Raycast Profile/Memory) | @rjsf/core Apache-2.0 (форма профиля) | данные памяти | 5 | S |

## 27. Меню
| # | Идея | Модуль, лицензия | ИИ-команда / данные | Вау | Сл. |
|---|---|---|---|---|---|
| 27.1 | Радиальное pie-меню по удержанию (игровые HUD) | Motion MIT | быстрые разделы | 8 | S |
| 27.2 | Док с увеличением иконок (macOS) | Motion MIT | список разделов | 7 | S |
| 27.3 | Стеклянная нижняя панель (iOS 26) | liquid-glass-react MIT | навигация | 8 | S |

## 28. Пульт
| # | Идея | Модуль, лицензия | ИИ-команда / данные | Вау | Сл. |
|---|---|---|---|---|---|
| 28.1 | Телефон-джойстик и геймпад | nipplejs MIT | управление сценой | 7 | S |
| 28.2 | Физический MIDI-контроллер крутит параметры (Teenage Engineering, teenage.engineering) | webmidi Apache-2.0 | параметры сцены и громкость | 8 | M |
| 28.3 | Телефон-указка: пара по QR, WebRTC | peerjs MIT + qrcode MIT (пара по QR, телефон шлёт данные гироскопа) | наведение на проекторе | 8 | M |
| 28.4 | Точечно-матричный стиль и моно-шрифты как у TE и Nothing | @fontsource/doto OFL-1.1 (точечный шрифт) | оформление | 7 | S |

## 29. Меню/поиск по командам
| # | Идея | Модуль, лицензия | ИИ-команда / данные | Вау | Сл. |
|---|---|---|---|---|---|
| 29.1 | Палитра по Ctrl/Cmd+K с превью справа (Raycast, Linear) | cmdk MIT или kbar MIT | запуск любой команды | 8 | S |
| 29.2 | Не команда? Отправить в чат (Raycast Quick AI fallback) | cmdk | запрос уходит в чат | 7 | S |
| 29.3 | Недавние и частые, нечёткий поиск, голосовой ввод | Fuse.js Apache-2.0 | история команд | 6 | S |

## 30. Трансляция на проектор
| # | Идея | Модуль, лицензия | ИИ-команда / данные | Вау | Сл. |
|---|---|---|---|---|---|
| 30.1 | Окно сразу на второй экран | broadcast-channel MIT (связь окон) | «выведи на проектор» | 7 | S |
| 30.2 | Ambient-режим: только сцена, без интерфейса, экран не гаснет | nosleep.js MIT | «режим атмосферы» | 9 | S |
| 30.3 | Вид докладчика с заметками | Reveal.js MIT | показ раздела | 6 | S |
| 30.4 | Коррекция перекоса картинки по четырём углам | perspective-transform MIT + CSS matrix3d | калибровка | 7 | M |

## Сквозные фишки (10)
| # | Фишка | Модуль, лицензия | Вау | Сл. |
|---|---|---|---|---|
| F1 | Фон реагирует на голос: громкость и спектр микрофона/TTS в uniform шейдера и орбиты планет | tone MIT (Analyser), three MIT | 9 | S |
| F2 | Жесты руками: щипок = выбор, ладонь = STOP, свайп = смена раздела (hand-tracking демо) | @mediapipe/tasks-vision Apache-2.0 | 9 | M |
| F3 | Пространственный звук: уведомления и голос приходят из места раздела на сцене | resonance-audio Apache-2.0 | 8 | M |
| F4 | Haptics: короткие паттерны на события (ответ, ошибка, STOP) | ios-haptics MIT (проверить поведение на Android) | 6 | S |
| F5 | Живые обои: единый store состояния ИИ (эмоция, нагрузка, мысль) питает uniform всех сцен | zustand MIT, three.js MIT | 9 | M |
| F6 | Ambient-режим проектора: через N минут тишины интерфейс гаснет, остаются обои и часы | nosleep.js MIT | 8 | S |
| F7 | Параллакс от головы или гироскопа (visionOS-ощущение глубины) | @mediapipe/tasks-vision Apache-2.0 (Face Landmarker) | 8 | M |
| F8 | Единая палитра команд на любой странице, плюс голос | cmdk MIT | 8 | S |
| F9 | Одна liquid-glass система токенов для всех разделов | liquid-glass-react MIT, style-dictionary Apache-2.0 | 8 | S |
| F10 | Звуковая идентичность UI: микрозвуки на события в стиле Teenage Engineering | Tone.js MIT, Howler MIT | 7 | S |

## Топ-15 для дизайнеров (вау / сложность, S=1, M=2, L=3)
| Место | Идея | Вау | Сл. | Индекс |
|---|---|---|---|---|
| 1 | F1 Фон реагирует на голос | 9 | S | 9.0 |
| 2 | 2.4 Liquid-glass панели | 9 | S | 9.0 |
| 3 | 3.1 Ambilight в кинотеатре | 9 | S | 9.0 |
| 4 | 4.1 MilkDrop-визуализатор butterchurn | 9 | S | 9.0 |
| 5 | 9.4 Голосовой орб | 9 | S | 9.0 |
| 6 | 13.1 3D-граф памяти | 9 | S | 9.0 |
| 7 | 19.1 Жидкая капля-эмоция | 9 | S | 9.0 |
| 8 | 30.2 Ambient-режим проектора | 9 | S | 9.0 |
| 9 | 29.1 Палитра команд Cmd+K | 8 | S | 8.0 |
| 10 | 27.1 Радиальное меню | 8 | S | 8.0 |
| 11 | 18.2 Сердцебиение звуком и светом | 8 | S | 8.0 |
| 12 | 22.2 Дуги связей на глобусе | 8 | S | 8.0 |
| 13 | 5.3 Новости на глобусе cobe | 8 | S | 8.0 |
| 14 | 24.3 Листание PDF 3D-переворотом | 8 | S | 8.0 |
| 15 | F8 Палитра команд везде | 8 | S | 8.0 |

Следующий эшелон (вау 9, сложность M, индекс 4.5): F2 жесты, F5 живые обои, 4.4 планеты как частоты, 6.1 фото в 2.5D, 3.2 кино-зал в 3D, 8.3 курсор ИИ на доске, 17.1 поток мыслей.

## Реестр пакетов (npm и лицензия, сверено `npm view <имя> license` 25.11.2026)
Ссылка на пакет: https://www.npmjs.com/package/<имя>. Исключения вне npm: ComfyUI (github.com/comfyanonymous/ComfyUI, GPL-3.0, запуск без Docker, для 7.1); GitHub-демо hand-tracking: github.com/collidingScopes/threejs-handtracking-101 (MIT).
Убраны из-за лицензий: jassub (LGPL/GPL), typed.js (GPL-3.0), imgly background-removal и audioMotion (AGPL), tldraw.

| Пакет | Лицензия | Ссылка |
|---|---|---|
| three | MIT | https://www.npmjs.com/package/three |
| ogl | Unlicense | https://www.npmjs.com/package/ogl |
| @paper-design/shaders | Apache-2.0 | https://www.npmjs.com/package/@paper-design/shaders |
| tone | MIT | https://www.npmjs.com/package/tone |
| motion | MIT | https://www.npmjs.com/package/motion |
| @xyflow/react | MIT | https://www.npmjs.com/package/@xyflow/react |
| react-markdown | MIT | https://www.npmjs.com/package/react-markdown |
| html-to-image | MIT | https://www.npmjs.com/package/html-to-image |
| codemirror | MIT | https://www.npmjs.com/package/codemirror |
| gridstack | MIT | https://www.npmjs.com/package/gridstack |
| embla-carousel | MIT | https://www.npmjs.com/package/embla-carousel |
| liquid-glass-react | MIT | https://www.npmjs.com/package/liquid-glass-react |
| fast-average-color | MIT | https://www.npmjs.com/package/fast-average-color |
| vidstack | MIT | https://www.npmjs.com/package/vidstack |
| hls.js | Apache-2.0 | https://www.npmjs.com/package/hls.js |
| @huggingface/transformers | Apache-2.0 | https://www.npmjs.com/package/@huggingface/transformers |
| butterchurn | MIT | https://www.npmjs.com/package/butterchurn |
| meyda | MIT | https://www.npmjs.com/package/meyda |
| lrc-kit | MIT | https://www.npmjs.com/package/lrc-kit |
| wavesurfer.js | BSD-3-Clause | https://www.npmjs.com/package/wavesurfer.js |
| rss-parser | MIT | https://www.npmjs.com/package/rss-parser |
| @mozilla/readability | Apache-2.0 | https://www.npmjs.com/package/@mozilla/readability |
| cobe | MIT | https://www.npmjs.com/package/cobe |
| kokoro-js | Apache-2.0 | https://www.npmjs.com/package/kokoro-js |
| @orama/orama | Apache-2.0 | https://www.npmjs.com/package/@orama/orama |
| img-comparison-slider | MIT | https://www.npmjs.com/package/img-comparison-slider |
| pixi.js | MIT | https://www.npmjs.com/package/pixi.js |
| pixi-filters | MIT | https://www.npmjs.com/package/pixi-filters |
| konva | MIT | https://www.npmjs.com/package/konva |
| tweakpane | MIT | https://www.npmjs.com/package/tweakpane |
| style-dictionary | Apache-2.0 | https://www.npmjs.com/package/style-dictionary |
| colorjs.io | MIT | https://www.npmjs.com/package/colorjs.io |
| @excalidraw/excalidraw | MIT | https://www.npmjs.com/package/@excalidraw/excalidraw |
| @excalidraw/mermaid-to-excalidraw | MIT | https://www.npmjs.com/package/@excalidraw/mermaid-to-excalidraw |
| yjs | MIT | https://www.npmjs.com/package/yjs |
| y-webrtc | MIT | https://www.npmjs.com/package/y-webrtc |
| @dnd-kit/core | MIT | https://www.npmjs.com/package/@dnd-kit/core |
| tinykeys | MIT | https://www.npmjs.com/package/tinykeys |
| frappe-gantt | MIT | https://www.npmjs.com/package/frappe-gantt |
| dagre | MIT | https://www.npmjs.com/package/dagre |
| d3 | ISC | https://www.npmjs.com/package/d3 |
| d3-shape | ISC | https://www.npmjs.com/package/d3-shape |
| @schedule-x/calendar | MIT | https://www.npmjs.com/package/@schedule-x/calendar |
| chrono-node | MIT | https://www.npmjs.com/package/chrono-node |
| suncalc | BSD-2-Clause (github.com/mourner/suncalc) | https://www.npmjs.com/package/suncalc |
| 3d-force-graph | MIT | https://www.npmjs.com/package/3d-force-graph |
| vis-timeline | Apache-2.0 OR MIT | https://www.npmjs.com/package/vis-timeline |
| markdown-it | MIT | https://www.npmjs.com/package/markdown-it |
| ts-fsrs | MIT | https://www.npmjs.com/package/ts-fsrs |
| uplot | MIT | https://www.npmjs.com/package/uplot |
| @xterm/xterm | MIT | https://www.npmjs.com/package/@xterm/xterm |
| sonner | MIT | https://www.npmjs.com/package/sonner |
| cytoscape | MIT | https://www.npmjs.com/package/cytoscape |
| lindenmayer | MIT | https://www.npmjs.com/package/lindenmayer |
| @rive-app/canvas | MIT | https://www.npmjs.com/package/@rive-app/canvas |
| canvas-confetti | ISC | https://www.npmjs.com/package/canvas-confetti |
| echarts | Apache-2.0 | https://www.npmjs.com/package/echarts |
| maplibre-gl | BSD-3-Clause | https://www.npmjs.com/package/maplibre-gl |
| pmtiles | BSD-3-Clause | https://www.npmjs.com/package/pmtiles |
| globe.gl | MIT | https://www.npmjs.com/package/globe.gl |
| d3-celestial | BSD-3-Clause | https://www.npmjs.com/package/d3-celestial |
| lightweight-charts | Apache-2.0 | https://www.npmjs.com/package/lightweight-charts |
| d3-sankey | BSD-3-Clause | https://www.npmjs.com/package/d3-sankey |
| pdfjs-dist | Apache-2.0 | https://www.npmjs.com/package/pdfjs-dist |
| tesseract.js | Apache-2.0 | https://www.npmjs.com/package/tesseract.js |
| page-flip | MIT | https://www.npmjs.com/package/page-flip |
| pdf-lib | MIT | https://www.npmjs.com/package/pdf-lib |
| @uppy/core | MIT | https://www.npmjs.com/package/@uppy/core |
| file-type | MIT | https://www.npmjs.com/package/file-type |
| fuse.js | Apache-2.0 | https://www.npmjs.com/package/fuse.js |
| nipplejs | MIT | https://www.npmjs.com/package/nipplejs |
| webmidi | Apache-2.0 | https://www.npmjs.com/package/webmidi |
| peerjs | MIT | https://www.npmjs.com/package/peerjs |
| qrcode | MIT | https://www.npmjs.com/package/qrcode |
| broadcast-channel | MIT | https://www.npmjs.com/package/broadcast-channel |
| nosleep.js | MIT | https://www.npmjs.com/package/nosleep.js |
| reveal.js | MIT | https://www.npmjs.com/package/reveal.js |
| perspective-transform | MIT | https://www.npmjs.com/package/perspective-transform |
| cmdk | MIT | https://www.npmjs.com/package/cmdk |
| kbar | MIT | https://www.npmjs.com/package/kbar |
| @mediapipe/tasks-vision | Apache-2.0 | https://www.npmjs.com/package/@mediapipe/tasks-vision |
| resonance-audio | Apache-2.0 | https://www.npmjs.com/package/resonance-audio |
| zustand | MIT | https://www.npmjs.com/package/zustand |
| howler | MIT | https://www.npmjs.com/package/howler |
| @ricky0123/vad-web | ISC | https://www.npmjs.com/package/@ricky0123/vad-web |
| tsparticles | MIT | https://www.npmjs.com/package/tsparticles |
| simplex-noise | MIT | https://www.npmjs.com/package/simplex-noise |
| @fontsource/doto | OFL-1.1 | https://www.npmjs.com/package/@fontsource/doto |
| ios-haptics | MIT | https://www.npmjs.com/package/ios-haptics |
| typewriter-effect | MIT | https://www.npmjs.com/package/typewriter-effect |
| @rjsf/core | Apache-2.0 | https://www.npmjs.com/package/@rjsf/core |
