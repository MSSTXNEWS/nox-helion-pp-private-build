# WIDGETS30: топ-30 виджетов AI-чатов и план подключения (C, 25.11)
Источники обзора: Vercel AI Elements (ai-sdk.dev/elements/components), assistant-ui (assistant-ui.com/elements), Cloudscape generative-AI chat pattern (cloudscape.design/patterns/genai/generative-AI-chat), AI Chat UI best practices (dev.to), Flutter AI Toolkit UX. Сайт NOX на ванильном JS + Shoelace, поэтому берутся не React-компоненты, а библиотеки-первоисточники.
Колонка П: Парето-очередь (1 = подключаем сейчас, 2 = следом, 3 = позже). Статус: есть / делаем / позже.

| № | Виджет | Готовая библиотека | П | Статус |
|---|---|---|---|---|
| 1 | Markdown-рендер ответа | marked (MIT) + DOMPurify (Apache-2/MPL) | 1 | проверить наличие в chat.html |
| 2 | Подсветка кода | highlight.js / Shiki | 1 | проверить |
| 3 | Копировать код / ответ | Clipboard API (нативно) | 1 | есть/проверить |
| 4 | Перегенерировать ответ | свой, base в /api/turn | 1 | есть |
| 5 | Остановить генерацию | /api/turn/stop | 1 | есть |
| 6 | Ответить / цитировать | nox-chat-rq.js (S1) + chat_core reply_to/quote | 1 | есть |
| 7 | Блок «Додумал» (reasoning/thinking) | sl-details (Shoelace) | 1 | есть (w30+) |
| 8 | Источники и цитаты-ссылки у ответа | sl-badge + meta.sources | 1 | есть |
| 9 | Уверенность / проверено судьями | sl-badge + meta.confidence/judges | 1 | есть |
| 10 | Быстрые ответы (chips) | sl-button pill, meta.quick | 1 | есть |
| 11 | Подсказки-автодополнение (Ghost-Tab) | NOXGhost | 1 | во всех полях: делаем |
| 12 | Шаблоны промптов с закреплением 📌 | /svc/advisors/pin | 1 | есть |
| 13 | Лайк/дизлайк | /api/feedback | 1 | есть |
| 14 | Индикатор «думает»/стадии | level-события SSE | 1 | есть |
| 15 | Плашка «Без памяти» | флаг incognito | 1 | есть |
| 16 | Память: «что ты помнишь» | /память, /mem/list | 1 | есть |
| 17 | Формулы | KaTeX (MIT) | 2 | позже |
| 18 | Диаграммы | Mermaid (MIT) | 2 | позже |
| 19 | Графики/таблицы | Chart.js (MIT) / sortable table | 2 | позже |
| 20 | Artifacts: превью HTML/кода в панели | sandbox iframe + sl-drawer | 2 | позже |
| 21 | Голосовой ввод/вывод | STT :8093 / TTS :8094 | 2 | есть в voice |
| 22 | Вложения/drag-and-drop | /api/upload (есть в chat_core) | 2 | есть |
| 23 | Предпросмотр ссылок | OpenGraph через сервер | 3 | позже |
| 24 | Системные виджеты: сервер, GPU, обучение | /data/arbiter.json, /api/nox/status | 1 | колонка 5: делаем |
| 25 | Погода/время/калькулятор карточки | open-meteo (без ключа) | 3 | позже |
| 26 | Поиск по диалогам | FTS5/Fuse.js (Apache-2) | 2 | позже |
| 27 | Ветвление/правка сообщения | base в /api/turn | 2 | есть частично |
| 28 | Тулколлы-карточки (что делает агент) | sl-details + события | 2 | позже |
| 29 | Горячие клавиши / командная палитра | ninja-keys / свой | 3 | позже |
| 30 | Экспорт диалога (md/pdf) | /экспорт | 3 | есть для памяти |

План Парето: пункты П=1 уже закрывают ~80% ценности; 1–3 проверить по chat.html и подключить недостающие через CDN-независимые локальные копии (vendor/), без правки web_server.py.
