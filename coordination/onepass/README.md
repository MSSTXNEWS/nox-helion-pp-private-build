# NOX WEB V29.3 — ONEPASS acceptance (no mock release)

This is an **integration overlay for the actual frozen 1,089-file V29.3 WEB**, not a new backend or a second model. Keep original ZIP immutable (SHA256 `166becb90fce63e2db3f9a74281d756995844552cddb7b67a0ac4bd67a190aa0`).

The derived ZIP (`NOX_HELION_WEB_V29_3_ONEPASS_VERIFIED.zip`, SHA256 `e70f0439fdf0a028c1d52fc638a38086aa7863fb7b33733a9609532dd544a9d5`) contains all 1,089 original paths and one new functional JS. Exactly five original HTML pages get a script tag; 1,084 original entries remain byte-identical. The original 13 native selection controls are now presented as accessible, live black-gold graphical buttons which trigger their **existing `input`/`change`** handlers and preserve form values. Dynamically populated voice options are handled by MutationObserver; reduced-motion styling included. Offline Chromium (actual derived HTML loaded via set_content) exercised 5 pages, 13 controls, mode and translation changes plus dynamic source options. This is NOT a physical owner Windows acceptance.

## One continuous finish, not another duplicate patch

1. Validate exact frozen ZIP and enumerate all 92 API callsites using `python -m coordination.onepass.frozen_web_contract --zip <original> --output report.json`.
2. Derive complete UI archive using `python -m coordination.onepass.build_choice_overlay --source <original> --output <derived> --script coordination/onepass/nox_choice_buttons_v293.js --manifest receipt.json`.
3. Keep the V132 canonical S03 dual-SHA fix already in the feature branch; do **not** replay the parallel V126 or stale V125 owner-fact writers. Prove original V130 M2 owner HTTP/S03 readback separately after access is restored.
4. Provider access recovery is **read only**: `python -m coordination.onepass.vast_official_readonly` inside the configured owner GitHub workflow (only official Vast CLI/SDK, no guessed URL). Currently SDK returned HTTP 404 and CLI did not confirm the instance. Do not infer that the instance or weights are deleted.
5. Resume physical NOX only after authorized original OneHost readback: current bridge/proxy SHA, owner cookie, 8080+8081 health, S03 quick_check, STOP, idle slots, backups and an independently verified restore. Never create a second backend or server.
6. Complete **69 unmatched URL contracts at the correct host** (existing OneHost vs Windows owner PC vs consent-required external provider); registered URLs alone do not count as functional E2E. Then finish Windows owner browser/EXE, physical GPU STOP and full-weight no-adapter optimizer/checkpoint restore gates.

## Release policy

The last grounded physical census remains **23 exact native routes out of 92**; 69 have no direct native match in that snapshot. V132 source fixes the original S03-internal-hash vs submitted-content-hash confusion. No full 92-route, Windows or no-adapter model release should be marked PASS without physical acceptance. Do not merge to production `main` on source CI alone.

Read machine-readable gate state in `NOX_WEB_V293_ONEPASS_MASTER.json`; retrieve original frozen WEB from [canonical Drive source](https://drive.google.com/file/d/1mRWUd7zwHNdJqTGelX7o0uSRSoNXyh01/view), and check [earlier native chat/S03 evidence](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43650605385) plus [official provider recovery audit](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43653284425).


## Дополнение ONEPASS: совместимость старого WEB-чата с настоящим OneHost (2026-11-15)

Исходный `/api/nox/chat` на страницах музыки и PC-kit использует старые форматы JSON/SSE, тогда как существующая проверенная модель NOX принимает `POST /api/nox/chat/stream` и возвращает NDJSON. Не создавать вторую модель или новый чат. `nox-legacy-chat-bridge-v293.js` перехватывает **только** запросы старого пути **только** при `window.NOX_NATIVE_OWNER === true` внутри `/nox-web-v29/` и направляет их через существующий сервер; остальные `fetch` и Windows-режим не меняются.

Native owner-диалог создаётся через действующий `/api/ui/memory/dialogs/create`. Успех выдаётся лишь после `saved=true`, `s03_integrated=true` и сравнения реальных двух последних сообщений `/api/ui/memory/dialogs/history`; частичный поток, отказ авторизации и незавершённая запись возвращают HOLD, без имитации сохранения. SSE kit-вызов сохраняет оригинальные `input`/`change` и получает проверку `done` только для owner-stage.

**Сборка:** `python -m coordination.onepass.build_legacy_compat_v2 --base NOX_HELION_WEB_V29_3_ONEPASS_VERIFIED.zip --output NOX_HELION_WEB_V293_ONEPASS_NATIVE_COMPAT.zip --script coordination/onepass/nox-legacy-chat-bridge-v293.js --receipt native_compat_receipt.json`. База V1 SHA-256 `e70f0439fdf0a028c1d52fc638a38086aa7863fb7b33733a9609532dd544a9d5`; результат 1091 файл, SHA-256 `45893adaf1fa49991dbb9f61f3d5cc4f2273eddf5d6f2e2548cf57d0b09fb947`; из 1090 исходных файлов 1075 побайтово не изменены. Добавлено 14 HTML подключений и один защищённый native owner SSE клиент.

**Проверено:** исходный frozen ZIP CRC/хеш; 10/10 Node VM фикстуры, 8/8 Chromium фикстуры, ZIP CRC, 14 правильных относительных путей, статическая сохранность. См. `NOX_V293_NATIVE_COMPAT_ACCEPTANCE.json`. **НЕ подтверждено:** физический ответ с Vast #60509551 после доступа HTTP 404, реальное 92/92 API, Windows EXE, физический GPU STOP, полная дистилляция весов и checkpoint restore. Source-only PASS не заменяет native E2E; не переключать production `main`.
