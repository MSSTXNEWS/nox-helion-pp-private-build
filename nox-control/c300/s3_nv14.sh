S=/workspace/nox/web/site; R=$S/qa/rework
post(){ curl -s -m 20 -X POST localhost:8091$1 -H 'Content-Type: application/json' -d "$2" | head -c 300; echo; }
echo "== NV14"
TOK=$(curl -s -m 10 -X POST localhost:8091/api/cmd/confirm -H 'Content-Type: application/json' -d '{"name":"svc.restart","clicked":true}' | /workspace/nox/venv/bin/python -c "import sys,json;print(json.load(sys.stdin).get('confirm_token',''))")
echo "T token len ${#TOK}"
echo "T navidrome before: $( (echo > /dev/tcp/127.0.0.1/4533) 2>/dev/null && echo up || echo down)"
echo "T restart:"; post /api/cmd "{\"name\":\"svc.restart\",\"params\":{\"service\":\"navidrome\"},\"confirm_token\":\"$TOK\"}"
sleep 10; echo "T navidrome after: $( (echo > /dev/tcp/127.0.0.1/4533) 2>/dev/null && echo up || echo down) http $(curl -s -m 5 -o /dev/null -w '%{http_code}' 127.0.0.1:4533/svc/navidrome/)"
echo "T token reuse:"; post /api/cmd "{\"name\":\"svc.restart\",\"params\":{\"service\":\"navidrome\"},\"confirm_token\":\"$TOK\"}"
cp $R/nav.fixed $R/nav.fixed.bak_s3_11 2>/dev/null
cat > $R/nav.fixed <<'N'
NAV.FIXED (S3: навигация, шапка, док, пульт, Ctrl+K, лупа). Обновлено 2026-11-25. Файл nav.html нет: страницы и шаги проверки ниже.

1. МЕНЮ
- nav.json: 72 -> 33 пункта, 11 категорий дока (КОНСТРУКТОР, КИНОТЕАТР, АТЕЛЬЕ, ПОМОЩНИК, ДОСКА, РЕЗОНАНС, МУЗЫКА, ГОЛОС, ЦВЕТ СЦЕНЫ, ЭФФЕКТЫ, ВИДЖЕТЫ) + СИСТЕМА (8 пунктов шапки: Диспетчер, Загрузки, Обучение, Память | Система, Проекты, Установка, Настройки). Добавлена «Лента» (glance.html) в ВИДЖЕТЫ.
- Дубли страниц (resonance, planets, creative, ai-learning, weights, g01-status, g07-hardware, events) редиректят на основные. План: qa/menu_plan.md. Бэкап оригинала: nav.json.bak_s3_1.
- Стеклянные выпадающие списки дока: иконка+название+описание, звезда избранного, недавние, шторка на мобильном.

2. ШАПКА (исправлено в этом раунде)
- Причина обрезки: .tb-l выровнен по правому краю, а 7 лишних иконок (nox-menu-x.css) на music/news/studio не скрывались; кроме того на 1200-1700 px правая колонка шире экрана. Правила перенесены в nox-unify.css (маркеры S3-HDR, S3-HDR2): компактные пункты 10px, без иконок в подписях, overflow:hidden, scrollLeft=0.
- Проверка чистым контекстом (service_workers=block), страницы music, cinema, settings, ширины 1200/1280/1366/1440/1536/1600/1700/1920: левый край шапки 206-456 px (>=0), правый край 1153-1721 px (< ширины экрана), scrollLeft=0, переполнения 0.
- Кеш: ссылки nox-unify.css, nox-menu-x.css, nox-nav-x.js получили ?v=s3_<время>, кеш service worker переименован (nox-s1-v3-s3b).
- Крошка «МУЗЫКА / МУЗЫКА»: в nox-nav-x.js совпадающие имена группы и страницы показываются один раз. music: «МУЗЫКА».
- 4K: zoom 1.3/1.55/1.95/2.3 (2200/2560/3200/3700 px), страница не уже ~1670 css px, шапка и док внутри экрана на 3840.

3. ПУЛЬТ, ЛУПА, КОМАНДЫ
- Чёрное солнце: клик открывает пульт (STOP, Быстро/Авто/Глубоко, голос, сенсоры, Транслировать, Второй экран, Полный экран, Концентрация, Проектор, Тест уведомл., Жесты, Громкость). Удержание 0.45 с: радиальное меню.
- Ctrl+K / лупа: избранное, недавние, страницы, команды реестра (русские синонимы), блок Meilisearch (серверный прокси search.meili, ключ не уходит в браузер; снимок по запросу «память»: «Meilisearch · nox»).
- Реестр qa/registry.json: команды ui.state, volume, projector, focus, notify.test, svc.restart (confirm), search.meili, persona.set, persona.get.
- svc.restart: рецепты jellyfin, navidrome, freshrss, ntfy, filebrowser, meili, web; без confirm_token 403, неизвестный сервис 400. Прогон через confirm-flow для navidrome см. итог в конце файла.

4. СТРАНИЦЫ И ШАГИ ПРОВЕРКИ (Playwright, 1440x900, затем 1280, 390x844, 3840x2160)
1) /web/index.html: шапка 4 пункта слева, чёрное солнце, лупа/звезда/колокол/заметки, 4 пункта справа; ничего не обрезано.
2) Те же проверки на /web/music.html, cinema.html, news.html, studio.html, settings.html, chat.html, board.html, creative.html, glance.html.
3) Клик по солнцу: пульт открыт; второй клик: закрыт.
4) Док: 11 ячеек (#nxdock .nxd-cells a); клик КИНОТЕАТР: список с иконкой, названием, описанием; клик по пункту: переход.
5) Ctrl+K: не открыта при загрузке; открывается по Ctrl+K и по лупе; «проектор», «громкость», «стоп»: команды сверху; «память»: блок Meilisearch; Esc закрывает; опасная команда просит подтверждение.
6) Кнопка назад и жесты, переход через View Transition.
7) 390 px: шапка сворачивается в солнце, лупа остаётся, шторка дока по долгому нажатию.
8) 3840 px: innerWidth/zoom >= 1650, правый край шапки и дока <= innerWidth.
9) /web/music.html: крошка «МУЗЫКА» один раз. /web/glance.html: рамка Glance с часами, календарём, новостями, рынками.

5. НЕ СДЕЛАНО / ЧЕСТНО
- Камера жестов MediaPipe не проверялась. 100 анимаций (архив с Диска) не распакованы.
N
echo "T nav.fixed $(wc -c < $R/nav.fixed) bytes"
cat >> $R/settings.fixed <<'N'

== S3 личность применяется (2026-11-25) ==
- chat_core.py: перед историей каждого хода добавляется system-сообщение из persona.json (system_hint); флаги: поле enabled в persona.json (по умолчанию true) и NOX_PERSONA=0 отключает. Бэкап chat_core.py.bak_s3_10. Тест одного сообщения через /api/chat: ответ получен (backend rte), health 200. Ядро BRAIN не менялось.
- Панель: persona.get возвращает core_reads=true, надпись «Применяется: подсказка добавляется в системный промпт каждого сообщения чата». Оговорка: проверено, что запрос проходит; влияние на тон ответа глазами не оценивал.
N
