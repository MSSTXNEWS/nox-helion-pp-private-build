# HANDOFF исполнителя A (NOX HELION, ТЗ «Топ-10 WOW»)
Работа: репо MSSTXNEWS/nox-helion-pp-private-build, копия /home/claude/nox-helion-pp-private-build. Хелпер /home/claude/run.sh <имя>
(берёт файлы из /home/claude/stage_<имя>/, push, dispatch nox-c300.yml, лог -> /home/claude/out_<имя>.txt). Исходники: nox-control/c300/a_src/.
## Сделано (всё на сервере, проверено Playwright, ошибок нет кроме п.«Известное»)
- 0. qa_audit.py (сервер + c300): NICHE по новой таблице, REG-пункт «модули из реестра», страницы consciousness/organism/soul/growth/selffeel/training, баллы A/R/U >=8, прокликивание всех button.
- 1. nox-fx.js/css на 65 html (кроме страниц B): tsParticles-пепел, GSAP-переходы/появление блоков, Motion-нажатие, тема Shoelace, HUD Arwes (vendor/nox-fx/hud.js).
- 2. chat.html: vendor/nox-chat-ui (React-бандл: рассуждение, ветки ‹1/2›, артефакты справа, источники, React Flow карта мышления #nuiFlow, голос Deep Chat #nuiVoice). Реальная отправка в Playwright прошла, карта строит 3 узла.
- 3. nox-brain-x.js/css + vendor/nox-brain (3d-force-graph) + vendor/llm-viz (статика, basePath /web/vendor/llm-viz, wasm пропатчен): consciousness (3D-разрез + органы), organism (лента ECharts с перемоткой + граф), soul (граф), growth, selffeel (радар+шкалы+орб), training (логи). Данные пишет /workspace/nox/tools/nox_a_feed.py (nohup) в site/data/organs_hist.jsonl и train_logs.json.
- Лицензии проверены по LICENSE: react, xyflow, assistant-ui, deep-chat, 3d-force-graph, three, arwes, cosmos.gl, esbuild, llm-viz = MIT; echarts = Apache-2.0; GSAP (уже в проекте) = Standard no-charge (не MIT!).
## Известное / не доделано
- HUD Arwes: createFrame вызывается, но .nox-hud = 0 на страницах (проверить сигнатуру createFrame/Settings, ошибки в hud.js).
- assistant-ui установлен, но не использован как рантайм (свои компоненты по его паттернам); cosmos.gl не подключён (взят 3d-force-graph).
- Не проверены: ветви ответа (нужен regen), артефакты, голос; скриншоты ПК/моб не сняты; audit.json по моим разделам не запускался; .fixed не созданы.
- index.html (п.4, Gridstack-стиль) не начат: смотреть nox-home-x.js, vendor/gridstack.
- Обмен с B: проверить его страницы (voice, music, photo, studio, knowledge, news, cinema), мелкое чинить, крупное в qa/rework/<р>.json; после правок nav.json -> qa_ctl.py --pin. Правило владельца: A/R/U>=8, кликать все кнопки, минимум своего кода.
## Следующие шаги
1. Скрипт: Playwright скрины (ПК 1440x900, моб 390x844, base64 q38) по 8 страницам, посмотреть, поправить.
2. Починить HUD; проверить regen/ветки/артефакт в чате.
3. index.html по реестру. 4. .fixed в site/qa/rework/<р>.fixed, python /workspace/nox/qa_audit.py <р>.html, до 3 циклов.
## Команды
Бэкапы *.bak_a_1 рядом с правленными. Рестарт: /workspace/nox/web/pkg/server/run_web.sh restart. Сборка: /workspace/nox/build_a (node PATH=/workspace/nox/tools/node/bin, node_modules/.bin/esbuild).
