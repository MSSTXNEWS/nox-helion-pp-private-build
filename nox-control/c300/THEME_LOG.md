# THEME_LOG (TH): тема «Графит»

## Пакет gr1: тема + кнопки
- Тема по умолчанию «Графит» (html[data-nox-theme=graphite]); «Солнце (классика)» = nox.ui.theme=sun (или ?theme=sun), прежний вид без изменений.
- Токены: шкала Radix Colors slate dark (MIT) --gx-1..12; акцент серебристо-голубой #9db1d1 (--cy 157,177,209); янтарь --am 224,184,120 малыми дозами; success #6cc59a, warn #e0b878, danger #e5736b; Shoelace --sl-color-primary/neutral/success/warning/danger, --sl-focus-ring, --sl-input-*.
- Фон: noise (SVG feTurbulence), радиальные градиенты, сетка 64px с маской, аврора 90 с (reduced-motion: статично). #space/#dust скрыты, сцена three.js в Графите не запускается (guard в nox-wow-bg.js).
- Авто-карта nox-graphite-map.css: th_gen_map.py дублирует каждое правило всех CSS и <style> сайта с тёплым цветом под html[data-nox-theme=graphite] с цветом в серо-голубой гамме (красные «danger» не трогает). Пересобирается скриптом деплоя; после крупных правок CSS другими агентами повторить: python3 th_gen_map.py SITE SITE/nox-graphite-map.css.
- ECharts-тема nox: серая палитра (патч nox-ds.js). Команды палитры: «Тема: Графит», «Тема: Солнце» (nox-actions.js). Переключатель: карточка «Тема» в Настройки > Интерфейс (nox-theme.js), localStorage nox.ui.theme, тема ставится до отрисовки (document.write link в head).
- Кнопки: .nx-btn (primary/secondary/ghost/danger/icon; sm 32, md 36, lg 44), sl-button и разовые кнопки страниц сведены глобальным CSS (радиус 8, фокус-кольцо 2px, мягкие hover/active/disabled).
- Не охвачено: стили, которые JS пишет inline/в <style> во время работы; страницы без nox-theme.js (operators, live, *-s1.main).
- Изменённые файлы: nox-theme.js, nox-wow-bg.js, nox-ds.js, nox-actions.js (бэкапы *.bak_th_<ts>), новые nox-graphite.css, nox-graphite-map.css.
- Снимки: nox-control/c300/screens_th/ (before_* до, btn_* и after_* после).
- Откат: gh workflow run nox-c300.yml -f script=th_rb_gr1.sh (восстановит бэкапы, удалит css), либо у пользователя: localStorage nox.ui.theme=sun.
