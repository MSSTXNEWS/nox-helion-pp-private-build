# NOX HELION V30 MAX READY — ЕДИНЫЙ КАТАЛОГ СКАЧАННОГО И ПАТЧЕЙ
Дата: 13.11.2026 · instructions_version 0.0.6 · SOURCE ONLY, не installed release.

## Каноническая папка
[NOX HELION EXPRESS INTEGRATOR](https://drive.google.com/drive/folders/1ewQ-R7z33fN0fKoMNNuFzv1_3rCEP96v).

Основной GitHub [PR251](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/pull/251). Исходный код и тесты хранятся там; архив — фиксированный snapshot для передачи/восстановления. [V29 ONEPASS MAX — предыдущая безопасная копия](https://drive.google.com/file/d/1bJpn2u5mPw6Pyiy1EJqLX4a137UPNC2i/view).

## Что входит
1. Весь текущий источник PR251: nox_runpod/teacher_mesh (GENESIS, HUNT V27, V28 WOW150, 24 шаблона, P02→S03, kernel/learning, тесты, V30 ABI gate), nox_runpod/web_wow_merge (оригинальный D02/WEB source merger, CHAT V25, Windows staging, OnePass, QA).
2. Оригинальные native OneHost, P02 ChatBridge, S03, WormAutopilot/Swarm/IdeaLoop/Providers из закреплённого SHA PR162: 56eddf293717851ae08585ce12dccda23fadeaa3. Исходники не объявляются развернутыми в рабочем Windows.
3. [NOX MASTER CATALOG — 200 исходников](https://drive.google.com/drive/folders/180zabWv3mn0tPI3k7BLgA2frf4zSRRjF): физические архивы, модели и справка по внешнему API OpenRouter. Уже сохранённые 69 базовых частей, 11 recovery ZIP, 52 новых частей/манифестов.
4. V29 source downloads — 14 дополнительных репозиториев, including torchao, torchtune, flashinfer, LMCache, xgrammar, EvalPlus, RULER, OpenCompass, tau2-bench и др. Архивы/манифесты в NOX MASTER CATALOG, без автоматической установки.
5. V30 source downloads — 5 новых инструментов agent reinforcement / evaluation: microsoft/agent-lightning, langchain-ai/deepagents, NVIDIA/garak, promptfoo/promptfoo, pydantic/pydantic-ai. Для двух крупногабаритных источников допустим npm/PyPI официальный дистрибутив вместо полного Git-дерева; происхождение и ограничения указаны в индексах. Не означает 5/5 полных Git-repo.

## Новые V30 патчи и code
- stage1_p02_s03_rag.py — привязка к существующему P02 ChatBridge.rag_context через авторизованные owner callbacks. Вопрос о съеденных учителях превращается в retrieval по проверенной M7; STOP, scope и private data защищены.
- v30_student_weight_abi_gate.py — допуск frozen teacher только по source SHA, лицензии, VM/isolation, точному student model SHA; никакой математически невозможной смеси весов. Для продления обучения требуются exact tokenizer/architecture, реальный optimizer, checkpoint, anti-forgetting и SAFE70.
- test_v30_student_weight_abi_gate.py — 12 тестов отклонения fake training, отсутствующих прав и несовместимых весов.
- download_v30_unique_sources.py — только pinned GitHub SHA, ZIP CRC, hash; не запускает скачанный код.
- download_v30_registry_fallback.py — защищённый срез npm/PyPI для слишком больших репозиториев, registry SHA256/SHA512.
- stage0_source_lock.py / stage1_memory_witness.py — сохранение эталона и ретроспективная проверка S03.

## Исходный WEB, чат и веса отдельно
- [WEB V25.1](https://drive.google.com/file/d/1cNt9FYth9K9dNihLi-ixIxdRgJy05mzV/view).
- [CHAT PC V25](https://drive.google.com/file/d/1bORWgKORNkeFkWIEIsWhSKq6sQJ8f_M6/view), [CHAT V24](https://drive.google.com/file/d/1XfWLP4wrFzvKioxdbZH-adAgwJZ9n3Nu/view), [ONEPASS V2](https://drive.google.com/file/d/1TWXd7YSufzRjNF2MCydVEqGYzVHw2Q6x/view).
- WEB Genesis staged ZIP SHA 829173a42a2ba42586328c6c810a5334f2332e1b6a856aec96088f5053cf1ca9. Source-only acceptance; D02 original SHA f3fc804d238146ffe42c50103d3e04c9736b8b587c6572987f59b61a6112eb17.
- Сохранённые веса, checkpoints и S03 не трогать и не удалять до независимого принятия нового canonical checkpoint.

## Статусы и физическая приёмка
SOURCE VERIFIED — байты + source/CRC/SHA checks. CI PASS — исходные тесты, не установленный Windows. STAGING — настоящий объединённый ZIP, без переписывания production. GPU TRAINED — только изменённые веса ученика + optimizer+checkpoint+readback+holdout+reload. WINDOWS E07 PASS — только independent same SHA на настоящем Windows OneHost/S03/voice/STOP. Текущие physical GPU / Windows E07 не подтверждены. Не считать source packages самостоятельным умом или доказательством сознания.

## Последовательность следующей интеграции
0 SourceLock, 1 реальный OneHost scoped-S03 retrieval и restart, 2 TTFT p95 и same-harness бенчмарки, 3 независимые учителя в VM, 4 student Forge checkpoint и anti-forget, 5 6 lanes+20 virtual worms native idle tick, 6 E07/rollback. Никаких новых backend, скрытых платных GPU запусков и автоматического исполнения чужого кода.
