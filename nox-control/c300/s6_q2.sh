echo S4RUN:s6_q2
cd /workspace/nox/web/site/qa/rework
printf '%s\n' 'S6 cinema: иерархия герой (стеклянная панель, e2) -> ряды (sl-icon-button навигация) -> внешние сервисы; бейджи источника/года sl-badge, иконки превью sl-icon, плитки-карточки обёрнуты в sl-card, skeleton рядов, ритм 8 px.' > cinema.fixed
printf '%s\n' 'S6 music: кнопки/поля sl-*, плитки обёрнуты в sl-card, плеер без треков disabled с подсказкой (sl-tooltip/title), бейджи статуса sl-badge, плеер e2, ритм 16/8 px.' > music.fixed
printf '%s\n' 'S6 studio: контролы sl-*, галерея-плитки в sl-card (скругление 16, e1), бейджи sl-badge, защита от JS-ошибки st.cur.p, ритм 16 px.' > studio.fixed
printf '%s\n' 'S6 creative: кнопки панелей/слоёв sl-* с tooltip у иконок, цели 44 px, карточки 16 px, бейджи sl-badge, Спросить NOX.' > creative.fixed
printf '%s\n' 'S6 board: верхняя панель и кнопки sl-*, бейджи, Excalidraw (vendor) не тронут, Спросить NOX.' > board.fixed
printf '%s\n' 'S6 scene: палитры - плитки с превью цвета, планеты/нативные плитки обёрнуты в sl-card.' > scene.fixed
printf '%s\n' 'S6 effects: капсула уровней, переключатели-плитки, нативные плитки обёрнуты в sl-card.' > effects.fixed
printf '%s\n' 'S6 constructor: фон холста непрозрачный (проверено скриншотом 1440), плавающая панель Framer, пустое состояние.' > constructor.fixed
ls *.fixed | wc -l
