# FEATURES100: 100 вау-фишек для K2 (креативщик-внедренец, 25.11.2026)

Метод: за отведённое время реально открыты и прочитаны ~20 страниц (помечены ✓: Raycast 2.6-2.13, Linear Pulse/Priority/Dashboards/Collapsible/UI refresh, NotebookLM Studio, ChatGPT Pulse, Figma, Krea, Grafana, Awwwards 2025 через Readymag и 3 сайта-победителя). Остальные источники (○) указаны по знанию продукта и ведут на главную: глубокую страницу не открывал. Заявленные «300 сайтов» не набраны: честный охват ~40 продуктов.

Сортировка: вау / сложность (S=1, M=2), затем вау. Не повторяет IDEAS.md. Все модули есть в vendor, остальное чистый CSS/JS на nox-ds (только sl-* контролы, цели 44 px, шрифт от 12 px).

Команды: NOXcmd = шина команд nox-cmd.js; /api/chat = запрос к ядру.

| № | Фишка | Где подсмотрено | Страница NOX | Модуль vendor | Связь с ИИ | Вау | Сл. |
|---|---|---|---|---|---|---|---|
| 1 | Голосовой шар с волнообразной амплитудой | [ChatGPT ○](https://chatgpt.com) | voice | ogl + paper-design-shaders | — | 9 | S |
| 2 | Вложить скриншот текущего раздела из меню «+» в композере | [Raycast 2.13 ✓](https://www.raycast.com/changelog/windows/2-13) | chat | html-to-image | NOXcmd «посмотри экран» → /api/chat | 8 | S |
| 3 | Drill-down: клик по сегменту графика раскрывает строки под ним | [Linear Dashboards ✓](https://linear.app/changelog/2025-07-24-dashboards) | finance | echarts events | /api/chat «объясни выброс» | 8 | S |
| 4 | Шаблон «Studio-плитки»: 4 плитки (аудио, видео, карта, отчёт) над списком результатов | [NotebookLM Studio ✓](https://blog.google/technology/google-labs/notebooklm-video-overviews-studio-upgrades/) | knowledge | shoelace card | NOXcmd «сделай обзор» | 8 | S |
| 5 | Peek: предпросмотр ссылки в плавающем окне без ухода со страницы | [Arc обзор ✓](https://www.howtogeek.com/888738/ways-arc-transforms-your-web-browser-experience/) | news | shoelace dialog + readability | «кратко по ссылке» | 8 | S |
| 6 | Живые карточки погоды-циклона на глобусе | [Windy ○](https://www.windy.com) | atlas | earth | «покажи ветер» | 8 | S |
| 7 | Облёт города 3D по команде | [Google Maps/Earth ○](https://earth.google.com) | atlas | maplibre-gl pitch/bearing | NOXcmd «облети X» | 8 | S |
| 8 | Fantastical: языковая вставка события с живым разбором слов цветом | [Fantastical ○](https://flexibits.com/fantastical) | calendar | chrono-node | NOXcmd «встреча завтра» | 8 | S |
| 9 | GitHub: тепловой календарь активности организма за год | [GitHub ○](https://github.com) | growth | d3 + echarts calendar | «покажи активность» | 8 | S |
| 10 | Раскладка «мягкий взгляд»: при наведении на карточку соседние чуть отступают и тускнеют (focus-follow) | [visionOS ○](https://developer.apple.com/visionos/) | index | CSS + motion | «сфокусируй X» | 7 | S |
| 11 | Заметка в чат по ⌘J (отправить текущее в чат) | [Raycast changelog ✓](https://www.raycast.com/changelog) | index | tinykeys | NOXcmd «спроси про это» | 7 | S |
| 12 | Приоритетный входящий: два потока «сейчас» и «подождёт» | [Linear Priority inbox ✓](https://linear.app/changelog/2026-09-03-priority-inbox) | index | sortablejs | NOXcmd «что срочно» | 7 | S |
| 13 | Кнопки «curate for tomorrow»: выбор тем завтрашней сводки | [ChatGPT Pulse ✓](https://openai.com/index/introducing-chatgpt-pulse/) | news | shoelace | /api/chat профиль тем | 7 | S |
| 14 | Карточки-обновления: расширить, спросить дальше, сохранить | [ChatGPT Pulse ✓](https://openai.com/index/introducing-chatgpt-pulse/) | index | embla-carousel | NOXcmd «глубже» | 7 | S |
| 15 | Универсальный поиск: проекты, люди, файлы одним окном | [Figma what's new ✓](https://www.figma.com/whats-new/) | index | kbar / fuse.js | NOXcmd «найди» | 7 | S |
| 16 | Редактор кривой easing для переходов интерфейса | [Figma what's new ✓](https://www.figma.com/whats-new/) | design | tweakpane | NOXcmd «замедли анимации» | 7 | S |
| 17 | Генеративные слайдеры атрибутов изображения | [Krea product ✓](https://www.krea.ai/news/product) | photo | pixi-filters + tweakpane | «теплее на 20%» | 7 | S |
| 18 | Плейлист дашбордов: авторотация экранов для телевизора | [Grafana what's new ✓](https://grafana.com/docs/grafana/latest/whatsnew/) | system | swiper + nosleep.js | NOXcmd «режим стены» | 7 | S |
| 19 | Аннотации на графике: пометить событие вертикальной линией | [Grafana what's new ✓](https://grafana.com/docs/grafana/latest/whatsnew/) | finance | echarts markLine | «отметь событие» | 7 | S |
| 20 | Текст песни вживую с подсветкой слов, увеличение строки | [Apple Music Sing ✓](https://techcrunch.com/2022/12/06/apple-music-is-getting-a-new-karaoke-like-feature-apple-sing) | music | lrc-kit | — | 7 | S |
| 21 | Цветной фон страницы по обложке (динамический акцент) | [Spotify ○](https://www.spotify.com) | music | fast-average-color | — | 7 | S |
| 22 | Главы на таймлайне с миниатюрами и название главы | [YouTube ○](https://www.youtube.com) | cinema | vidstack | «найди момент про X» | 7 | S |
| 23 | Слои карты: переключатель ветра, температуры, давления | [Windy ○](https://www.windy.com) | atlas | maplibre-gl + earth | «включи слой X» | 7 | S |
| 24 | Маршрут анимацией линии с бегущим огоньком | [Apple Maps ○](https://maps.apple.com) | atlas | maplibre-gl + d3-shape | «построй путь» | 7 | S |
| 25 | Ночная сторона Земли с терминатором | [Google Maps/Earth ○](https://earth.google.com) | atlas | cobe / earth + suncalc | — | 7 | S |
| 26 | Страницы-блоки со слэш-меню «/» | [Notion ○](https://www.notion.so/product) | assistant | blocknote | «вставь блок X» | 7 | S |
| 27 | Перплексити-источники: чипы с favicons и номерами сносок | [Perplexity ○](https://www.perplexity.ai) | news | CSS | /api/chat с цитатами | 7 | S |
| 28 | Related-вопросы: три чипа продолжения под ответом | [Perplexity ○](https://www.perplexity.ai) | chat | shoelace | NOXcmd «спроси дальше» | 7 | S |
| 29 | Магический плюс: перетащить кнопку «+» в любое место списка | [Things 3 ○](https://culturedcode.com/things/) | projects | sortablejs | «добавь задачу» | 7 | S |
| 30 | Робинхуд: цифры тикают как барабан, линия рисуется при движении пальца | [Robinhood ○](https://robinhood.com) | finance | echarts + gsap | — | 7 | S |
| 31 | Copilot Money: круговой «бюджет месяца» с остатком по дням | [Copilot Money ○](https://www.copilot.money) | finance | d3-shape | «сколько осталось» | 7 | S |
| 32 | Datadog: тепловая карта хостов цветными плитками | [Datadog ○](https://www.datadoghq.com) | system | echarts treemap | NOXcmd «где перегруз» | 7 | S |
| 33 | Eve Online: радарное кольцо ближних событий | [Eve Online ○](https://www.eveonline.com) | organism | d3-shape | — | 7 | S |
| 34 | Discord: статус-присутствие «играет в…» у ИИ (что он делает сейчас) | [Discord ○](https://discord.com) | soul | CSS + zustand | NOXcmd «чем занят» | 7 | S |
| 35 | Anki: оценка карточки Снова/Трудно/Хорошо/Легко с интервалами | [Anki ○](https://apps.ankiweb.net) | training | ts-fsrs | NOXcmd «повтори» | 7 | S |
| 36 | Acrobat: подсказка «спроси документ» по выделению | [Adobe Acrobat ○](https://www.adobe.com/acrobat.html) | pdf | pdfjs | NOXcmd «объясни абзац» | 7 | S |
| 37 | Stripe Sessions: градиентная сетка фон реагирует на курсор | [Stripe Sessions site ○](https://stripe.com/sessions) | index | paper-design-shaders | — | 7 | S |
| 38 | visionOS: окна «парят» с тенью и глубиной при наклоне мыши | [visionOS ○](https://developer.apple.com/visionos/) | index | CSS perspective | — | 7 | S |
| 39 | Счётчик расхода ИИ: полоса оранжевеет, потом краснеет | [Raycast changelog ✓](https://www.raycast.com/changelog) | system | CSS + echarts | /api/chat usage | 6 | S |
| 40 | Сворачиваемые блоки «>>>» в длинных ответах и заметках | [Linear Collapsible ✓](https://linear.app/changelog/2025-03-19-collapsible-sections) | chat | shoelace details | — | 6 | S |
| 41 | Слушать аудио-обзор и читать карту одновременно (мини-плеер поверх) | [NotebookLM Studio ✓](https://blog.google/technology/google-labs/notebooklm-video-overviews-studio-upgrades/) | knowledge | howler + wavesurfer.js | — | 6 | S |
| 42 | Inspect-панель: типографика, цвет, границы с копированием в один клик | [Figma what's new ✓](https://www.figma.com/whats-new/) | design | colorjs.io | «скопируй токен» | 6 | S |
| 43 | Мудборд и референсы стиля как стопка карточек | [Krea product ✓](https://www.krea.ai/news/product) | studio | sortablejs + fast-average-color | «в этом стиле» | 6 | S |
| 44 | Переменные дашборда: выпадашка меняет все графики | [Grafana what's new ✓](https://grafana.com/docs/grafana/latest/whatsnew/) | system | shoelace select + echarts | — | 6 | S |
| 45 | Дозированные «моменты движения» при прокрутке отчёта | [Awwwards 2025: Wakuli Impact ✓](https://wakuli-impact.com/) | finance | gsap ScrollTrigger | — | 6 | S |
| 46 | Спейсы и разделители вкладок: цветной контекст на страницу | [Arc обзор ✓](https://www.howtogeek.com/888738/ways-arc-transforms-your-web-browser-experience/) | index | style-dictionary | NOXcmd «режим работы» | 6 | S |
| 47 | Canvas: зацикленный фон-видео у трека | [Spotify ○](https://www.spotify.com) | music | CSS video | — | 6 | S |
| 48 | Сториз-полоски прогресса сверху и тап по краям | [Spotify ○](https://www.spotify.com) | growth | CSS + motion | — | 6 | S |
| 49 | Skip intro: кнопка пропуска и следующий эпизод с обратным отсчётом | [Netflix ○](https://www.netflix.com) | cinema | vidstack | NOXcmd «пропусти титры» | 6 | S |
| 50 | Режим кинотеатра: затемнение всего кроме плеера | [YouTube ○](https://www.youtube.com) | cinema | CSS | NOXcmd «погаси свет» | 6 | S |
| 51 | Мои места: пины со стикерами-эмодзи | [Apple Maps ○](https://maps.apple.com) | atlas | maplibre-gl markers | «запомни это место» | 6 | S |
| 52 | Рассуждение сворачивается в строку «думал N секунд» | [Claude.ai ○](https://claude.ai) | chat | shoelace details | — | 6 | S |
| 53 | Проекты с постоянной инструкцией и знаниями (как Projects) | [Claude.ai ○](https://claude.ai) | projects | fuse.js | NOXcmd «в проект X» | 6 | S |
| 54 | Гибкие ответы: «подумать подольше» и режимы глубины | [ChatGPT ○](https://chatgpt.com) | chat | shoelace select | /api/chat mode | 6 | S |
| 55 | Календарные наборы и «окно сегодня» в одну строку | [Fantastical ○](https://flexibits.com/fantastical) | calendar | schedule-x-calendar | «что сегодня» | 6 | S |
| 56 | Things: «Сегодня» с вечерним разделом и звёздочкой | [Things 3 ○](https://culturedcode.com/things/) | projects | sortablejs | — | 6 | S |
| 57 | Игровой HUD: угловые скобки и сканлайн на стеклянных карточках | [Destiny 2 / Cyberpunk HUD ○](https://www.cyberpunk.net) | consciousness | CSS clip-path + arwes-frames | — | 6 | S |
| 58 | Destiny-стиль плашки награды при достижении цели | [Destiny 2 / Cyberpunk HUD ○](https://www.cyberpunk.net) | growth | gsap + canvas-confetti | — | 6 | S |
| 59 | Slack: ответ в ветке боковой панелью | [Slack ○](https://slack.com) | chat | shoelace drawer | «ответь в ветке» | 6 | S |
| 60 | Duolingo: серия дней и огонь, вехи | [Duolingo ○](https://www.duolingo.com) | growth | lottie-web | — | 6 | S |
| 61 | Teenage Engineering: крутилки-энкодеры с рифлёной анимацией | [Teenage Engineering ○](https://teenage.engineering) | settings | tweakpane + CSS | — | 6 | S |
| 62 | FWA: частицы собираются в логотип при загрузке раздела | [FWA ○](https://thefwa.com) | index | tsparticles | — | 6 | S |
| 63 | Ответ ИИ и пустое окно ввода: «встряхнуть» поле при пустой отправке | [Raycast changelog ✓](https://www.raycast.com/changelog) | chat | CSS keyframes | — | 5 | S |
| 64 | Липкие шапки таблиц в ответах ИИ при прокрутке | [Raycast changelog ✓](https://www.raycast.com/changelog) | chat | CSS sticky | — | 5 | S |
| 65 | Кастомный toast с возможностью «больше не показывать» | [Raycast changelog ✓](https://www.raycast.com/changelog) | index | sonner | — | 5 | S |
| 66 | Вкладки «Для меня / Популярное / Недавнее» над лентой событий | [Linear Pulse ✓](https://linear.app/changelog/2025-04-16-pulse) | news | shoelace tab | /api/chat | 5 | S |
| 67 | Лайк/дизлайк на карточке и история отзывов | [ChatGPT Pulse ✓](https://openai.com/index/introducing-chatgpt-pulse/) | news | zustand | /api/chat обратная связь | 5 | S |
| 68 | Выбор всех объектов по цвету («target icon») | [Figma what's new ✓](https://www.figma.com/whats-new/) | design | fabric | «выдели синее» | 5 | S |
| 69 | Двойной тап перемотка 10 с с волной | [YouTube ○](https://www.youtube.com) | tv | nipplejs / pointer events | — | 5 | S |
| 70 | Фокус-режимы поиска: Всё / Академ / Видео / Соц | [Perplexity ○](https://www.perplexity.ai) | knowledge | shoelace radio | /api/chat scope | 5 | S |
| 71 | Кастомный стиль в виде кода: параметр --sref как чип | [Midjourney ○](https://www.midjourney.com) | studio | tweakpane | — | 5 | S |
| 72 | Голосовой клон: показ формы волны и ползунок «схожесть» (только своё) | [ElevenLabs (только приём) ○](https://elevenlabs.io) | voice | wavesurfer.js | — | 5 | S |
| 73 | Stripe: пульсирующий счётчик «деньги в движении» | [Stripe ○](https://stripe.com) | finance | gsap | — | 5 | S |
| 74 | Sonos/AirPlay: выбор устройства вывода с плавной сменой | [Sonos ○](https://www.sonos.com) | music | CSS + broadcast-channel | NOXcmd «на кухню» | 5 | S |
| 75 | Плавающая лента «Pulse»: что нового в организме за день, на тексте и аудио-дайджесте | [Linear Pulse ✓](https://linear.app/changelog/2025-04-16-pulse) | index | typewriter-effect + howler | NOXcmd «пульс дня» | 9 | M |
| 76 | Реалтайм-холст: рисуешь, рядом видишь результат | [Krea product ✓](https://www.krea.ai/news/product) | studio | fabric + pixi-filters | /api/chat «доработай» | 9 | M |
| 77 | Контент следует за движением курсора: фото смотрят на пользователя | [Awwwards 2025: People Look at Art ✓](https://space.repponen.com/peoplelookatart/) | photo | CSS + mediapipe-tasks-vision | «следи за мной» | 9 | M |
| 78 | Boosts: ИИ меняет вид любой страницы по описанию (CSS на лету) | [Arc обзор ✓](https://www.howtogeek.com/888738/ways-arc-transforms-your-web-browser-experience/) | design | codemirror | NOXcmd «перекрась страницу» | 9 | M |
| 79 | Daily DJ: ИИ-голос представляет подборку | [Spotify ○](https://www.spotify.com) | music | speechSynthesis + howler | NOXcmd «диджей» | 9 | M |
| 80 | Wrapped: итоги года как сториз с жестами | [Spotify ○](https://www.spotify.com) | growth | embla-carousel + canvas-confetti | NOXcmd «итоги месяца» | 9 | M |
| 81 | X-Ray: актёры и сцена по паузе кадра | [Apple TV ○](https://www.apple.com/apple-tv-app/) | cinema | vidstack + transformers-js | «кто в кадре» | 9 | M |
| 82 | Диффы правок ИИ: зелёные и красные строки с принять/отклонить | [Cursor ○](https://cursor.com) | assistant | codemirror merge | NOXcmd «правка» | 9 | M |
| 83 | Gemini Live: камера в голосовом диалоге, ИИ видит предмет | [Gemini ○](https://gemini.google.com) | voice | mediapipe-tasks-vision | «что это» | 9 | M |
| 84 | Rive: интерактивный талисман ИИ реагирует на состояния (думает, слушает) | [Rive showcase ○](https://rive.app/community) | chat | rive | статус хода /api/chat | 9 | M |
| 85 | @-упоминания: события календаря, заметки, контакты в поле ввода | [Raycast 2.13 ✓](https://www.raycast.com/changelog/windows/2-13) | chat | tinykeys + fuse.js | /api/chat с контекстом | 8 | M |
| 86 | Дашборд из перетаскиваемых панелей: график, таблица, одно число | [Linear Dashboards ✓](https://linear.app/changelog/2025-07-24-dashboards) | system | gridstack + echarts | NOXcmd «добавь на дашборд» | 8 | M |
| 87 | Интерактивная карта-ум из источников с раскрытием узлов | [NotebookLM mind map ✓](https://workspaceupdates.googleblog.com/2025/03/new-features-available-in-notebooklm.html) | knowledge | 3d-force-graph / cytoscape | NOXcmd «карта по теме» | 8 | M |
| 88 | Видеообзор-слайды: озвученная презентация из заметки | [NotebookLM Studio ✓](https://blog.google/technology/google-labs/notebooklm-video-overviews-studio-upgrades/) | pdf | reveal.js + speechSynthesis | NOXcmd «слайды из документа» | 8 | M |
| 89 | Karaoke-режим: ползунок громкости вокала | [Apple Music Sing ✓](https://techcrunch.com/2022/12/06/apple-music-is-getting-a-new-karaoke-like-feature-apple-sing) | music | tone (фильтр центра) | NOXcmd «убери вокал» | 8 | M |
| 90 | Сплит-вид: два раздела бок о бок | [Arc обзор ✓](https://www.howtogeek.com/888738/ways-arc-transforms-your-web-browser-experience/) | index | gridstack | NOXcmd «рядом с чатом» | 8 | M |
| 91 | Обратные ссылки и полупрозрачный граф вокруг заметки | [Obsidian ○](https://obsidian.md) | memory | cytoscape | NOXcmd «связи записи» | 8 | M |
| 92 | Холст заметок: карточки на бесконечном поле со стрелками | [Obsidian ○](https://obsidian.md) | memory | excalidraw-excalidraw | «разложи заметки» | 8 | M |
| 93 | Живой предпросмотр сгенерированного интерфейса | [v0 ○](https://v0.dev) | studio | iframe sandbox + codemirror | «собери форму» | 8 | M |
| 94 | Запись «Canvas»: справа редактируемый документ, ИИ правит выделение | [ChatGPT ○](https://chatgpt.com) | assistant | blocknote | NOXcmd «перепиши абзац» | 8 | M |
| 95 | Google Photos: Ask Photos — вопрос к своей галерее | [Google Photos ○](https://photos.google.com) | photo | transformers-js + orama-orama | NOXcmd «найди фото X» | 8 | M |
| 96 | Apple Photos: кинематографический «воспоминание-ролик» из подборки | [Apple Photos ○](https://www.apple.com/photos/) | photo | ffmpeg + howler | «сделай ролик» | 8 | M |
| 97 | Lightroom: маски — рисуешь область, правишь только её | [Lightroom ○](https://lightroom.adobe.com) | photo | fabric | «осветли небо» | 8 | M |
| 98 | Miro: курсоры участников с именами (ИИ-курсор по доске) | [Miro ○](https://miro.com) | board | yjs + CSS | «нарисуй со мной» | 8 | M |
| 99 | Приглушённые боковые панели: фокус на контенте (контраст по зонам) | [Linear UI refresh ✓](https://linear.app/changelog/2026-03-12-ui-refresh) | settings | CSS | — | 4 | S |
| 100 | Скорость 0.25–2× по удержанию | [YouTube ○](https://www.youtube.com) | cinema | vidstack | — | 4 | S |
