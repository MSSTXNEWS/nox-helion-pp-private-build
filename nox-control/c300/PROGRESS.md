# PROGRESS (WEB)
| Дата | Что | Где | Оценки / проверка |
|---|---|---|---|
| 26.11 | Тема Графит возвращена, ensure+webroot_sync в каждом деплое | site, pkg/webroot | M1 на всех 27 страницах |
| 26.11 | nox-u-ux (CTA, пустые состояния, 44 px) на 26 страницах + Writer | site | U ср. 7.10 (локальный замер, Lighthouse ещё не считан) |
| 26.11 | Оверлей 5 миров (nox-cinematic-worlds из FASTWOW) | 78 страниц | 0 JS-ошибок, graphite сохранён |
| 26.11 | Главная = FASTWOW index (V29.3 + пакет), старая в index-legacy.html | site/index.html | 1440 и 2560 отрисованы, 0 JS-ошибок; 390 не проверено |
| 26.11 | studio.html = конструктор FASTWOW (плитки миров/палитр), старая в studio-legacy.html | site/studio.html | см. ui_st3 |
| 26.11 | READY_MAP.md, FULL_MAP.md (84 страницы, 32 шаблонные заглушки) | nox-control/c300 | инвентарь |
| 26.11 | studio.html = конструктор FASTWOW (плитки 5 миров x 6 палитр, 0 select), старая studio-legacy.html; шрифты Tektur/Orbitron скопированы, 404 нет | site | 1440 и 390 отрисованы, 0 JS-ошибок |
| 26.11 | zip в v29src удалены; диск /workspace 17 ГБ свободно | server | df |
| 26.11 | Чат v4: подписи и прогресс в колонке «Система», воздух, фон; оверлей миров на чате отключён (ломал цвет и перекрывал) | chat-dc, nox-dc.css, nox-dc-cols.js | WOW на глаз ~6, замер vision не запускал |
| 26.11 | Чат v5: hero-приветствие (плитки быстрых запросов), типографика, шапка/кнопки 40 px (ch_dc30) | chat-dc, nox-dc.js/css | Lighthouse (desktop, нагруженный сервер): perf 36, a11y 100, BP 96; vision 1920: A8 R7 WOW6 (правая панель перегружена); axe: label critical x1, region x2 |
| 26.11 | Чат v6-v8: Система = 4 крупные метрики, Shoelace по idle, aria для полей, мобильная шапка/подложка (ch_dc34-36) | chat-dc | vision 1920/390: A8 R7 WOW6 (итерация 1 из 3 по vision) |
| 26.11 | nox-a11y-fix.js (aria-правки общих скриптов, Shoelace, FullCalendar, FilerobotImageEditor) на 78 страницах кроме index/chat-dc; откат ?a11y=0 | site, webroot | axe: settings 0, photo 1 minor, calendar 1 minor (было 5-7 с critical) |
| 26.11 | nox-frame.js: единый каркас Shoelace (sl-card, sl-tab-group при >=3 секций) на 27 шаблонных заглушках, откат ?legacy=1 | site, webroot | axe advisors/contacts/mail: 0 нарушений |
