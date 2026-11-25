# VENDOR_READY (исполнитель D, обновляется)
Статус 25.11: F-модули скачаны (node_modules в /workspace/nox/web/build), готовые сборки лежат в site/vendor/<имя>/. Полный список с версиями, лицензиями и примерами: VENDOR_INDEX.md и site/vendor/INDEX.json.
- Планеты: site/vendor/planets/{2k,8k}/ (Solar System Scope, CC BY 4.0, LICENSE и ATTRIBUTION.txt рядом). Есть Земля (день/ночь/облака), Луна, Марс, Юпитер, Сатурн + кольца (2k png), Венера (поверхность/атмосфера), Меркурий, Солнце; Уран и Нептун только 2k.
- Статические приложения: vendor/drawio, jupyterlite, earth, novnc, talkinghead, foliate-js.
- Бандлы: *.esm.js и *.iife.js (глобал NOX_<имя>), React-пакеты со своим React внутри.
- Из реестра IDEAS.md добавлены все пакеты, кроме kokoro-js (не нужен). ComfyUI не ставился.
- Известное: tremor требует Tailwind; stellarium-web-engine пропущен (emscripten, AGPL); arwes (frames/animated) см. INDEX, у A рабочая версия в vendor/nox-fx.
- S-сервисы: в работе, статус будет здесь.
