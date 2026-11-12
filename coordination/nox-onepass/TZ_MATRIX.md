# NOX HELION · сверка с ТЗ V16, пожеланиями владельца и GENESIS

Проверка: 2026-11-12T13:27:38.979866+00:00. Исходники: 292/292 SHA-256; **не** физическая Windows/GPU-приёмка.

Проверено 48 обязательных направлений: MISSING_FROM_BUNDLE 12, SOURCE_PRESENT 36. Статус SOURCE_PRESENT означает наличие исходника, НЕ готовую функцию.

| ID | Требование | Статус исходника | Что доказано / почему HOLD |
|---|---|---|---|
| P01-01 | One real Windows WPF/WebView2 EXE | MISSING_FROM_BUNDLE | No EXE file in 292-file bundle. Missing required source indicator, or supplied as native/remote component |
| P01-02 | Original living D02 asset intact | SOURCE_PRESENT | Pinned D02 source SHA-256 agrees. physical runtime not verified |
| P01-03 | Eight CoreID semantic controls | SOURCE_PRESENT | Original V20/V22 CORE binding; 8 objects in historical Chromium receipts. physical runtime not verified |
| P01-04 | 14 original world switches 6+5+3 | SOURCE_PRESENT | Original orbit control JS and physical-worlds; historical same checkout Chromium checked 14 centers. physical runtime not verified |
| P01-05 | 5 owner approved Persona without duplicates | SOURCE_PRESENT | Five SHA-pinned cropped portraits; visible in 1440 screenshot. V16 21.1 earlier said HOME only CoreIDs; newer explicitly approved V25.1 retains personas |
| P01-06 | Original approved HOME compositing | SOURCE_PRESENT | Owner HOME WEBP SHA-256 agrees. physical runtime not verified |
| P01-07 | Reduced Motion / ECO BALANCED MAX | SOURCE_PRESENT | Source CSS and orbit mode tokens. physical runtime not verified |
| P01-08 | 10 WEB routes available | SOURCE_PRESENT | 10/10 HTML files exist, static refs pass; prior Chromium 10/10. physical runtime not verified |
| P01-09 | No native select/dropdown controls | SOURCE_PRESENT | Zero <select> elements across 10 source HTML pages; dynamically injected controls not fully examined. physical runtime not verified |
| P01-10 | 14 worlds real HDRI/PBR | SOURCE_PRESENT | Original Three.js engine + 14 asset manifest hashes present. Physical Windows GPU shader/light/motion requires actual hardware |
| P01-11 | Responsive 320/390/800/1024/1440/1920/4K | SOURCE_PRESENT | Historical #43146688351 has 7/7 BROWSER_CANDIDATE (SwiftShader); this runtime Chromium blocked by administrator. Windows owner GPU acceptance not achieved |
| P01-12 | Global keyboard F11 Escape Ctrl+K | SOURCE_PRESENT | UI JS includes keyboard handlers; complete real use not tested. physical runtime not verified |
| P02-01 | Single Resonance chat UI | SOURCE_PRESENT | One chat route and native status API. physical runtime not verified |
| P02-02 | True OneHost NDJSON stream | SOURCE_PRESENT | Chat JS handles /api/nox/chat/stream and done; backend not bundled. physical runtime not verified |
| P02-03 | STOP with late token rejection | SOURCE_PRESENT | Web STOP signal handler exists; no physical/isolated test. physical runtime not verified |
| P02-04 | S03 SQLite WAL dialogs and restart durability | MISSING_FROM_BUNDLE | No real SQLite database in WEB ZIP; browser API wiring only. Missing required source indicator, or supplied as native/remote component |
| P02-05 | Full RU/ES ASR and TTS | SOURCE_PRESENT | Routes exist; native voice weights and RU/ES audio evidence absent. physical runtime not verified |
| P02-06 | RAG/attachment and source provenance | SOURCE_PRESENT | Client source selectors present; no index persistence test. physical runtime not verified |
| P02-07 | Isolated PersonaId memory and consent | SOURCE_PRESENT | Client persona/dialog separation path; ACL server unverified. physical runtime not verified |
| P03-01 | Native NSIS installer and rollback | MISSING_FROM_BUNDLE | No installer executable in this WEB ZIP. Missing required source indicator, or supplied as native/remote component |
| P03-02 | In-app software/model install UI | SOURCE_PRESENT | Installation navigation exists; native download and rollback not tested. physical runtime not verified |
| P03-03 | Model self-identity NOX only | SOURCE_PRESENT | Single NOX model passport UI; 24-model historical V16 contradicted by later ONE NOX decision. physical runtime not verified |
| P03-04 | Windows user-consented PC CONTROL | MISSING_FROM_BUNDLE | No Windows PC CONTROL bridge inside WEB ZIP. Missing required source indicator, or supplied as native/remote component |
| P04-01 | Real own student weights | MISSING_FROM_BUNDLE | No full student checkpoint weights included. Missing required source indicator, or supplied as native/remote component |
| P04-02 | Real full-parameter optimizer/checkpoint provenance | SOURCE_PRESENT | Read-only proof evaluator only; no actual optimizer or weights in bundle. physical runtime not verified |
| P04-03 | Background training and thermal SAFE70 | SOURCE_PRESENT | Web training status/controls only; cannot prove GPU scheduler, sensor or background loop. physical runtime not verified |
| P04-04 | GPU progress no fake percentage | SOURCE_PRESENT | Synthetic no-false-PASS source tests pass, not evidence of trained weights. physical runtime not verified |
| P04-05 | Checkpoint resume and Windows hash sync | MISSING_FROM_BUNDLE | No checkpoint 85 or Windows sync receipts in WEB bundle. Missing required source indicator, or supplied as native/remote component |
| P04-06 | S03 M0–M7 cognitive episodic memory | MISSING_FROM_BUNDLE | Backend neural memory implementation not contained in WEB ZIP. Missing required source indicator, or supplied as native/remote component |
| P04-07 | C01–C08 single functional reasoning engine | MISSING_FROM_BUNDLE | UI labels alone cannot prove cognitive engine. Missing required source indicator, or supplied as native/remote component |
| P04-08 | Teacher distillation with quality improvement | MISSING_FROM_BUNDLE | No data/gradients/optimizer/eval results and full SHA on student weight. Missing required source indicator, or supplied as native/remote component |
| P04-09 | One cognition no model picker | SOURCE_PRESENT | Single NOX UI; not proof of actual model absorption. physical runtime not verified |
| P05-01 | Real GPU/CPU/RAM sensors | SOURCE_PRESENT | Browser telemetry fetches existing API; no connected host data. physical runtime not verified |
| P05-02 | Honest external backend HOLD on static preview | SOURCE_PRESENT | Explicit honest preview label and progress HOLD. physical runtime not verified |
| P05-03 | FullCalendar functional cycle | SOURCE_PRESENT | Historical same SHA V19 browser scenario PASS; not independently rerun this session. physical runtime not verified |
| P05-04 | PhotoSwipe gallery lightbox | SOURCE_PRESENT | Historical same SHA V19 browser scenario PASS. physical runtime not verified |
| P05-05 | tsParticles real engine | SOURCE_PRESENT | Historical same SHA V19 browser scenario PASS. physical runtime not verified |
| P05-06 | PDF/EPUB/Shaka/Leaflet loaded and functional | SOURCE_PRESENT | Presence of libraries; complete E2E work flows not verified. physical runtime not verified |
| P05-07 | Physical Edge hardware screenshots | MISSING_FROM_BUNDLE | No physical Windows Edge/GPU accessible; historical Chromium is SwiftShader. Missing required source indicator, or supplied as native/remote component |
| P05-08 | NO-LOSS STOP and rollback physically accepted | MISSING_FROM_BUNDLE | Native training/DB and Windows rollback missing. Missing required source indicator, or supplied as native/remote component |
| P05-09 | No public production without acceptance | SOURCE_PRESENT | HOLD flag exists; cannot assert production environment from static bundle. physical runtime not verified |
| P05-10 | Physical side-by-side owner visual QA | SOURCE_PRESENT | Approved source and earlier 1440 screenshot compared; final owner signoff missing. physical runtime not verified |
| G-01 | One unmodified source artifact SHA across tests | SOURCE_PRESENT | Actual zip 292 paths & SHA256 agree with source manifest. physical runtime not verified |
| G-02 | No backend mocks, training fake PASS | SOURCE_PRESENT | Static proof correctly reports HOLD; runtime is not supplied. physical runtime not verified |
| G-03 | Independent Windows release/installer acceptance | MISSING_FROM_BUNDLE | No physical Windows/EXE and no signed binary artifact. Missing required source indicator, or supplied as native/remote component |
| G-04 | OnePass full physical verifier shipped | SOURCE_PRESENT | Windows Edge QA program included, not executed on owner hardware. physical runtime not verified |
| G-05 | WOW30 10+10+10 tracked | SOURCE_PRESENT | 30 criteria tracked; no independent physical 30/30 PASS evidence. physical runtime not verified |
| G-06 | OnePass reliable state and restarts | SOURCE_PRESENT | Runner and manual Windows launcher; no scheduled background service installed. physical runtime not verified |

## Последующие решения и конфликты

- Исходное ТЗ V16 §21.1 говорило HOME только с восемью CoreID, без Persona. Позднее утверждённый V25.1 содержит пять Persona на HOME: это не исходный дефект автоматически, нужно учитывать последнее прямое решение.
- V16 §21.5 описывает каталог 24–30 моделей, однако более позднее явное решение — единая личность NOX без пользовательского выбора учителей; не возвращать выпадающие списки моделей ради старого ТЗ.
- Наличие локального статического сайта не доказывает, что native Windows EXE, S03, модели и тренер доступны.
.
## Источники

- [Канон V16](https://docs.google.com/document/d/11EM0qW3PJN0WqV8Euc1A2X4c0UukHiVq_0WfaLYVYpc/edit)
- [Полная функциональная спецификация](https://docs.google.com/document/d/1g7JUanN5lz9ysxOzKO35wXxr399r0oEYQJ09R1hQFjg/edit)
- [GENESIS 0–4](https://docs.google.com/document/d/18YLAo_Cja3HJKZn6qr57P-zsm0-AHcx2aag0rgSjwS4/edit)
- [WEB V25.1 Browser CI](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43146688351)
- [ONEPASS V2 PR252](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/pull/252)