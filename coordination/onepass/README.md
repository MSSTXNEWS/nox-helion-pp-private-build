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
