Исходники новой сборки «Резонанс» (кино-HUD): chat.html + nox-wow*.js/css (+ wow/*.json lottie, nox-v14-planet.js с фото-текстурами). Старый чат остаётся в chat-classic.html.
Деплой на S1: s1_web_deploy.sh (сборка из ветки nox-web-dist) -> vendor_install.sh -> planets_s1.sh. Проверка: test/fakes.py + web_server.py + test/e2e.js (Playwright).
