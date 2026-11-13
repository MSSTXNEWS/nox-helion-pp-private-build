# ⚡ NOX HELION — ONEPASS MAX SOURCE CONSOLIDATION · 13.11.2026

## Где всё лежит
- [Каноническая папка NOX HELION EXPRESS INTEGRATOR](https://drive.google.com/drive/folders/1ewQ-R7z33fN0fKoMNNuFzv1_3rCEP96v).
- [Код и единая программа V27–V29 — GitHub PR #251](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/pull/251).
- [Архивный каталог 200 исходников / моделей](https://drive.google.com/drive/folders/180zabWv3mn0tPI3k7BLgA2frf4zSRRjF) — уже загружен (69 базовых частей, 11 recovery ZIP, 52 completion chunks/manifest files). Не скачивать повторно.
- [WEB V25.1](https://drive.google.com/file/d/1cNt9FYth9K9dNihLi-ixIxdRgJy05mzV/view) 12.9 МБ; [CHAT V25](https://drive.google.com/file/d/1bORWgKORNkeFkWIEIsWhSKq6sQJ8f_M6/view) 66.7 МБ; [ONEPASS V2](https://drive.google.com/file/d/1TWXd7YSufzRjNF2MCydVEqGYzVHw2Q6x/view).
- [V28 WOW150+24 templates](https://drive.google.com/file/d/1WyhIOQkTjwC2jJzr6l43CDcc8x-AsdTi/view); [Stage 00–01](https://drive.google.com/file/d/1ylDRba3gfiVp6iSxM45cyIL75UUGkRPd/view).

## Новый комплект MAX
- source_pr251/nox_runpod/teacher_mesh: ВСЕ текущие V27/V28/V29 модули, шаблоны и тесты.
- source_pr251/nox_runpod/web_wow_merge: реальный WEB/CHAT merger, Genesis/evidence bridge, D02 source QA, Windows staging.
- inherited_native_pr162: закреплённые исходники PR #162: оригинальные P02 ChatBridge/OneHost/S03, WormAutopilot/WormSwarm/IDEA/Provider, штатные адаптеры. Это не замена установленного NOX.
- traceability: все SHA, ссылки на модели/исходники, исторический benchmark и checklist.
- NOX_V29_EXTRA: добавочные реальные GitHub источники для квантования, ускорения, оценки и обучения. Отдельные source-only ZIP и манифесты SHA, без автоматической установки/исполнения.

## Готовый WEB-кандидат
В Vercel Sandbox nox-web-wow-merge-20261112 собран реальный NOX_WEB_WOW_V25_GENESIS_S03_SOURCE_CANDIDATE.zip, размер 76,189,556 байт, SHA-256 829173a42a2ba42586328c6c810a5334f2332e1b6a856aec96088f5053cf1ca9. Проверка CRC None, 1059 файлов, оригинальный D02 не изменён. Только SOURCE, не Windows E07. Оригинальные ZIP доступны в Drive и подлежат объединению через NOX_ONEPASS_GENESIS_V26_STAGING.cmd.

## План фактической приёмки 0–6
0 — SourceLock, D02 SHA, l03 historical benchmark. 1 — реальный P02→S03 history/memory без утечки scope, перезапуск Windows OneHost, M7. 2 — TTFT p95, токены/сек, IFEval/ruMMLU same harness. 3 — независимые замороженные учителя из VM, rights/privacy. 4 — настоящий optimizer, checkpoint RNG, изменённые student weights SHA, replay и SAFE70. 5 — native WormAutopilot/20 virtual worms, подписанная политика owner, действующий idle tick. 6 — Windows E07, WOW30, один NOX, один S03, безопасный rollback.

## Политика
Не создавать второй backend, вторую S03, ещё 20 OS-процессов или 17 видимых моделей. Не удалять checkpoints, модели или пользовательские чаты до доказанной замены. Не публиковать ключи/секреты. Изучать только законно доступные официальные репозитории, pin SHA/license; не запускать чужой код автоматически. Скачивание ≠ обучение, SOURCE CI PASS ≠ физический Windows / GPU PASS.
Исторический l03 11.11: GSM8K 88/100, IFEval 54/100, HumanEval 84/100, ruMMLU 117/200 — source report only, not current model.


## Реально дополнительно скачано: 14/14 внешних репозиториев, SOURCE VERIFIED

**Рабочая папка:** [NOX MASTER CATALOG](https://drive.google.com/drive/folders/180zabWv3mn0tPI3k7BLgA2frf4zSRRjF). Новые исходники не ставились в production и не обучали GPU. Использованы Git-коммиты, ZIP CRC, SHA-256; реестр лицензий помечен review-required.

- Группа kernels: 6 Git source archives (pytorch/ao, meta-pytorch/torchtune, safetensors/safetensors, LMCache/LMCache, mlc-ai/xgrammar, huggingface/optimum), 1 большая исходная ветка отдельно. Файлы: NOX_V29_EXTRA_kernels_INDEX.zip и NOX_V29_EXTRA_kernels_PART_00.zip.
- Группа benchmarks: evalplus/evalplus, NVIDIA/RULER, open-compass/opencompass, allenai/open-instruct, SWE-bench/SWE-bench, THUDM/LongBench. Файлы: NOX_V29_EXTRA_benchmarks_INDEX.zip, PART_00.zip и PART_01.zip.
- FlashInfer: исходники flashinfer-ai/flashinfer, exact Git SHA 168920874c95f1bc9888bdd015d13e056fa3a341, NOX_V29_LARGE_flashinfer_INDEX.zip и PART_00..03.zip.
- τ²-bench: исходники sierra-research/tau2-bench, exact Git SHA c06b07dd7c4d4ec61ba6ff9bcdf0b15dd7ef36d4, NOX_V29_LARGE_tau2_INDEX.zip и PART_00..02.zip.

CI: [14-репозиторная первая загрузка](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43314658703) SUCCESS (12/14 + two oversized HOLD, replaced by separate full archive) и [дозагрузка двух больших](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43315623058) SUCCESS (2/2). Сумма: 14/14 verified upstream source snapshots. Файлы на Drive: четыре манифеста плюс десять частей (14 физических ZIP), после загрузки Drive metadata проверены по именам/размерам. Полная обратная SHA-проверка всех байтов с Drive пока не проводилась.

**Сборка и проверка:** скачать ZIP всех четырёх групп и запустить скрипт reassemble_v29_extra_sources.py из этого пакета:
- python reassemble_v29_extra_sources.py <папка> — проверить части и общий SHA, без записи TAR.
- python reassemble_v29_extra_sources.py <папка> --assemble <пустая_папка> — физически собрать четыре TAR без автоматической распаковки чужого кода. Не перезаписывает файлы, не исполняет пакеты.

**Новый source-only P02→S03 adapter:** stage1_p02_s03_rag.py; tests/test_stage1_p02_s03_rag.py используют изолированную настоящую SQLite для контрактов native owner scope, STOP, обучения и проверенного исторического M7. Реальное P02/S03 подключение на Windows отдельно не проверено.

**Важно:** не выбирать TorchAO или torchtune как единственный активный тренер без проверки состояния сопровождения; это исследовательские исходники. Список источников ограничен полезными NOX репозиториями, а не буквальным «всем Интернетом».
