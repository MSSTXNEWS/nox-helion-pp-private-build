S=/workspace/nox/web/site
cd $S
cd /workspace/nox/web/site
for f in chat index voice; do cat >> qa/rework/$f.fixed <<'F'
Shoelace (S1, 25.11): оставшиеся родные кнопки, поля, списки, ползунки и переключатели показываются как sl-button, sl-input, sl-textarea, sl-select, sl-range, sl-switch (фасад nox-sl-s1.js: исходные элементы скрыты и получают click/change, код страниц не менялся). Сквозной прогон кнопок на 1440 и 390: без реакции 0 (эвристика: изменение DOM или запрос).
F
done
for f in assistant pdf atlas finance; do cat >> qa/rework/$f.fixed <<'F'
Сквозной прогон кнопок (S1, 25.11): на 1440 и 390 ни одной кнопки без реакции (эвристика: изменение DOM, запрос или переход). Исправлены ошибки консоли: конфликт AMD define (xterm грузится до Monaco), лишний nox-p-work.js на assistant.
F
done
echo ok
