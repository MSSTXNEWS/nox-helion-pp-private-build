# VENDOR_READY (исполнитель D, итог 25.11)
Каталог: VENDOR_INDEX.md (копия site/vendor/INDEX.json): 134 записи, 130 готовы. Подключение от корня сайта: ./vendor/<имя>/..., бандлы *.esm.js (ESM) и *.iife.js (глобал NOX_<имя>), React-пакеты со своим React внутри.
## Готово
- Планеты: vendor/planets/{2k,8k}/ (Solar System Scope, CC BY 4.0, LICENSE и ATTRIBUTION.txt). Земля (день/ночь/облака/нормали), Луна, Марс, Юпитер, Сатурн + кольца (2k png), Венера, Меркурий, Солнце, Млечный путь; Уран и Нептун только 2k.
- Shaka (shaka-player.ui.js + controls.css), dash.js, Vidstack (vidstack.esm.js, player/styles) и @vidstack/react: в vendor.
- Статические приложения: vendor/drawio, jupyterlite, earth (ветра: данные подкладывать самим), novnc, talkinghead (+GLB-аватары), foliate-js.
- Все пакеты реестра IDEAS.md кроме kokoro-js (не нужен); ComfyUI не ставился.
## Сервисы (127.0.0.1, прокси /svc/<имя>/, реестр svc_registry.json, бэкап .bak_d_1, старт в svc/start_d.sh из start_all.sh)
glance 18200 (уже стоял, делает S3), memos 18201, radicale 18202 (без пароля), beszel 18203, actual 18204, kuma 18205, stirling 18206 (Java 25 в svc/jre25), codeserver 18207, podcastfy 18208 (нужны ключи LLM/TTS), whisperlive 18209 (CPU torch, WebSocket; pyaudio не ставился).
Часть приложений не знает префикс /svc/ (режим strip): memos, kuma, actual, beszel могут отдавать абсолютные пути ассетов; проверять в рамке.
## Не встало
arwes-frames/animated (нужен motion@10; у A рабочая версия в vendor/nox-fx), rss-parser (серверный), stellarium-web-engine (emscripten, AGPL), Perplexica (нужен SearXNG, тяжело), omniclip/feishin (сборка не делалась), ACE-Step (после установки <25 ГБ диска), tremor без Tailwind-стилей.
