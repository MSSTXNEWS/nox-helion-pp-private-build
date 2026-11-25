S=/workspace/nox/web/site
cat > $S/qa/rework/creative.fixed <<'X'
DZ: creative.html переписан (Fabric 7 + Shoelace, nox-dz-creative.js/css): Figma-раскладка, 17 инструментов, слои/свойства/история, зум 3200% и пиксельная сетка, перо Безье, маска кистью/лассо, ИИ через /vision/describe (каракули -> слои SVG, текст остаётся Textbox), план с подтверждением, пресеты фотореализма, Ответить/Цитировать; генератор: честное «недоступно». QA 1440/390/4K: 0 ошибок JS, 0 мёртвых кнопок, цели >=44. Ластик пиксельный не сделан (нет EraserBrush в сборке Fabric), nox-ghost ждёт модуль S1.
X
ls -la $S/qa/rework/creative.fixed
