# NOX HELION · V28 · ПОЭТАПНОЕ ВНЕДРЕНИЕ · ЭТАПЫ 0–1
**Дата:** 13 ноября 2026 • **instructions_version:** 0.0.6
**Источник:** [PR #251](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/pull/251).
**Принцип:** один NOX, один OneHost, одна S03, один D02. Никаких новых backend, принудительного обновления весов, удаления моделей, переписывания оригинальных страниц.

## Этап 0 — базовый эталон (SOURCE LOCK)
**Зачем:** перед улучшением скорости, памяти, учителей и обучения закрепить один достоверный исходный набор.

Основания:
- [WEB V26 physical source acceptance](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/blob/feature/nox-teacher-mycelium-20261112/nox_runpod/web_wow_merge/NOX_V26_PHYSICAL_SOURCE_ACCEPTANCE_20261112.json): source ZIP SHA 9556b5…, Genesis staged ZIP SHA 829173…, D02 SHA f3fc804…, 1053/1053 неизменных исходников. Это отчёт SOURCE, не Windows E07.
- [BENCH_RESULTS_FINAL_1200MSK](https://drive.google.com/file/d/11i7cz37KzMHryTGnnNNNzqHtVlDY9VDv/view): NOX l03 SHA fee7cec…, GSM8K 88/100, IFEval 54/100, HumanEval 84/100, ruMMLU 117/200. Исторические **отчётные** значения, их нельзя приписывать текущему NOX или новой версии.
- [GENESIS 0–4](https://docs.google.com/document/d/18YLAo_Cja3HJKZn6qr57P-zsm0-AHcx2aag0rgSjwS4/edit), [WOW150 V28](https://drive.google.com/file/d/1WyhIOQkTjwC2jJzr6l43CDcc8x-AsdTi/view).
- 100 старых когнитивных/архитектурных идей + 50 новых WOW + 40 отдельных предложений: 190 пунктов **с перекрытиями**, а не 190 физически готовых функций.

Файлы:
- V28_STAGE_00_SOURCE_BASELINE_20261113.json: зафиксированный эталон, исходные ссылки и статусы HOLD.
- stage0_source_lock.py: SHA-256 фактических исходников текущего checkout, проверка V26-акта и исторической таблицы; optional --web-zip и --model-file для реально локально доступных файлов.
- test_stage0_source_lock.py: контроль подмены D02, ложного релиза и выдуманных бенчмарков.

Успешный результат означает только SOURCE_BASELINE_VERIFIED_RUNTIME_HOLD. Для Windows/OneHost/GPU приёмки по-прежнему HOLD. Сам скрипт никогда не перезаписывает C:\NOX.

## Этап 1 — реальная память NOX
**Цель:** на вопрос «Ты кого съел?» NOX извлекает проверенные события о конкретных учителях/дистилляциях. Через перезапуск OneHost эти воспоминания не теряются и не переходят между пользователями.

Что уже есть:
- cognitive_overlay.py с расширением вопросов («съел», «учитель», «дистилляция») и верификацией записи M7.
- s03_callback_adapter.py для исходной авторизованной S03.
- **Новое:** stage1_memory_witness.py формирует SHA-256 отпечаток проверенного S03 M7-события без экспорта полного текста; различает before/after boot ID и требует native reboot/readback receipt.

Для этого **действующий OneHost** обязан передать четыре вещи через доверенный код: owner-scope, фактический S03 callback, ожидаемый verified event ID, boot ID. Кнопка / текст модели не могут сами выдать себе эти полномочия.

Проверить на реальной Windows нужно:
1. До перезапуска задать NOX вопрос об учителях; убедиться, что **конкретный факт M7 подтверждён S03**, а не написан prompt'ом.
2. Сохранить witness SHA и boot ID без сохранения личного текста в CI.
3. Перезапустить реальный OneHost, а не только обновить вкладку браузера.
4. Повторить readback по тому же owner-scope, проверить digest и новый boot ID.
5. Проверить чужой scope, событие без verified flag и отсутствие S03: всё должно честно переходить в HOLD.
6. Запустить отдельную Windows E07 и прочесть её receipt. Даже одинаковые fingerprint и native signed reboot receipt **не являются независимым E07 PASS**.

Исходный test_stage1_memory_witness.py использует временную SQLite как учебный fixture, но не создаёт вторую реальную память NOX и не выполняет Windows reboot. Внешняя интеграция остаётся HOLD.

## Следующие этапы и строгая последовательность
- **2 — Скорость ответа и качество:** тот же student SHA и один GPU; Fast/Verify/Deep, TTFT p50/p95, tok/s, context caching, source-grounded RAG. Бенчмарки IFEval и ruMMLU сравнивать на одном dataset/split/harness.
- **3 — Teacher Arena:** ограниченная внешняя проверка, выбор полезного учителя, privacy, consent, независимый judge, knowledge corpus.
- **4 — Реальный FORGE:** лицензия, source-separated holdout, adapter/full weight update, реальные optimizer steps и checkpoint, merge, SHA, replay, anti-forgetting, SAFE70.
- **5 — 6 lanes + 20 worms:** связать уже существующие native worm autopilot/IDEA LOOP через действующий idle-tick, бюджет, STOP и readback; не порождать 20 отдельных LLM и не жечь GPU без задач.
- **6 — Release:** источник D02 без потерь, OneHost ↔ S03 ↔ Resonance, независимый Windows E07, rollback.

## Запуск source-аудита (без установки)
Из корня checkout PR #251:

~~~bash
python nox_runpod/teacher_mesh/stages/stage0_source_lock.py --out /tmp/NOX_STAGE0_SOURCE_RECEIPT.json
python -m unittest discover -s nox_runpod/teacher_mesh/stages -p 'test_stage*.py' -v
~~~

Отдельно можно передать --web-zip и --model-file, если файлы действительно доступны на проверяющей машине: утилита не скачивает их и не утверждает, что они активны. Для Windows используйте внешнюю папку отчётов вместо /tmp.

**Реальное состояние:** Stage 0 SOURCE; Stage 1 SOURCE tests; Windows S03/OneHost/EXE E07 HOLD. Ни одно утверждение в документе не означает субъективного сознания, успешно проведённой дистилляции или установленного релиза.
