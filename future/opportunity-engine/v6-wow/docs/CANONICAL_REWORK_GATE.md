# NOX HELION · OIE canonical integration gate · 2026-10-31

Scope: **OIE inside approved NOX**, not a new HOME/MENU/WORK. Supersedes the standalone V6 visual proposal as a release candidate; historical preview source remains for provenance only.

## Authority (checked against Drive)
- DESIGN MASTER V5: owner-approved HOME and SHA-locked original art; preserve immutable media.
- MENU+NAVIGATION V2: retain section IA, Function Lock and active route manifest.
- GOVERNANCE 144: especially rules 089–096 and 106–110; independent acceptance on same BuildID.

## Implementation
`engine/nox_canonical_panel.mjs` exports `mountOpportunityPanel(target, options)`.
Host creates an existing **approved** OIE route container with `data-nox-screen="opportunity-engine"`; this module never creates top-level navigation, asteroids, personas, or a competing Helion.
`options`: `apiBase` (read-only same-origin GET), `signal` (host cancel), `onBack`, `onEvent`, `requestJob(action, parameters, signal)` (trusted host IPC for privileged work).
The host **must** authorize and implement `requestJob` against existing `nox.oie.job.v1`; absent wiring returns `HOST_ACTION_NOT_CONNECTED`, never a false success. Do not inject tokens in markup or allow browser JS to grant consent.
No new release route or owner artwork is shipped in this future branch.

## Existing functionality retained
Catalog list, filter, 9-item pagination, inspector and escape, Ctrl+K focus, run 3 hypotheses, MB1 preview, back, errors, lifecycle/dispose. No publication, purchases, business launch, or fabricated sensor telemetry.

## Physical gate (still HOLD)
1. Integrator verifies approved routeId/parent section in authoritative menu manifest before mounting.
2. Verify original HOME/MENU/WORK image SHA-256 and PersonaIDs versus current Drive CANON.
3. Wire same-origin read-only API and authenticated host IPC; do not load independent V6 `studio_v6.html` into HOME.
4. Check R75 ten asteroid hit targets on actual original MENU image. CSS donor is unaccepted until pixel test.
5. Test full 193 navigation nodes separately from native handler claims, and cross-check 8 CoreIDs/5 PersonaIDs.
6. E07 installed Windows x64 test on **one** Setup SHA / EXE SHA / BuildID: STOP, history, real model, UI, ACL/consent/undo, DPI, keyboard, reduced-motion.
7. Only then update release status. Browser tests and GitHub file existence are not Windows E07 acceptance.

Status: SOURCE PATCH only; NO CLAIM of merged release, working Windows app or 100% fidelity.


## Source patch completion · 31 October 2026
Source: `engine/nox_canonical_panel.mjs`, test: `tests/test_canonical_panel.mjs`.
- The approved NOX shell creates an existing route's target; this panel **does not introduce a competing menu, asteroids, portraits or HOME**.
- Trusted `requestJob(action, parameters, signal)` handles **all four** existing OIE operations: `idea.list`, `idea.inspect` (parameter `idea_id`), `mission.run` and `megablock1.preview`. Return the existing `{ok, contract:'nox.oie.result.v1', result}` object. The host, not the panel, must enforce capability/ACL. Do not call privileged backend by untrusted HTTP token.
- If a trusted host callback is missing, sensitive actions and Back are disabled/HOLD. Read-only same-origin GET is allowed for standalone QA preview only, never to assert native integration.
- Shadow DOM keyboard Escape/Ctrl+K, focusable inspector, 9-item pagination, search, abort lifecycle, remount and API origin guard addressed.
- Regression: source module and the new behavior test were loaded directly from GitHub and evaluated in an isolated V8 DOM stub; **1 suite PASS** (multiple assertions). This is not Chromium/WebView2 visual QA and not Windows EXE evidence.

Actual release blockers verified 2026-10-31:
- Latest GitLab pipeline #3011902044 on R78 `fix/nox-r78-webview2-signature-20261031` is FAILED at `t06_local_onehost_bridge` / windows-compile; the job log contains **zero bytes**, so root cause is UNKNOWN. Do not misclassify as a source-code error.
- This future branch is not the release merge target. Only I0 may integrate after verifying exact HEAD and approved route/asset SHA. E07 acceptance must use one installed Setup/EXE SHA, BuildID, original asset hashes and full UI/function validation.

**Gate:** SOURCE PATCH READY FOR REVIEW; INTEGRATION HOLD; WINDOWS E07 HOLD; RELEASE BLOCKED. 


## ТЗ V16 / MASTER GOVERNANCE / DESIGN MASTER · сверка текущего выполнения, 31.10.2026

Это **адресная** сверка исходников и работающих контролей, НЕ заявление об инвентаризации каждого файла на Drive/GitHub/GitLab.

1. **Единый релиз:** актуальный основной интеграционный кандидат — GitHub PR #162, head `d35323b93c93a2bc3274aa1a2458f4cce7254e37`, 1075 изменённых путей (metadata only, не полный CONTENT_READ). В текущем PR #162 отсутствуют OIE/Opportunity именованные файлы среди изменённых путей. Изолированный PR #231 не является сборкой NOX.
2. **Пятёрка и WOW:** GitLab R78 `coordination/mega814/manifest.json` содержит 10 MENU10, 8 CoreID, 8 WORK, 5 PersonaID, 54 исходных routeId; `menu-v2-193.json` — 193 навигационных пункта. До 190 native handlers нет E07 evidence. Для Persona EV действует `IDENTITY_CONFLICT_HOLD`, для LA `BODY_HOLD`: их нельзя подменять новыми лицами.
3. **Единственная нативная граница:** оригинальные `nox_native_bridge` / `p02_native_ingress` закрепляют 50 PACK01 routes; E06 сейчас связывает `chat.model` и `models.installed`, read-only JS port — `chat.model` + `chat.stop`. OIE NOT bound in original native system.
4. **OIE безопасность:** создан `engine/native_owner_adapter.py` (Git blob `15a039be96d34c6fcc36ae712c13a85cb9ce7add`). Точные байты совпали с локально исполненным исходником, Python compile PASS, 15 positive/negative assertions PASS. Adapter imports canonical `NativeSession`, requires separate E06 native `authorize`, delegates only `idea.list`, `idea.inspect`, `mission.run`, `megablock1.preview` into existing `run_job`; no new DB/server/50+ route. **This does NOT mean WPF ↔ Python integration exists.**
5. **Win CI:** canonical PR #162 head workflows (six checked) all concluded failure; checked D02 job returned zero steps; CircleCI combined status ERROR. GitLab pipeline #3011902044 (R78) failed in `t06_local_onehost_bridge`, job log zero bytes. Root cause **UNKNOWN** (allocation/permissions/runner policy hypotheses, not asserted). Cannot claim new BuildID, EXE SHA or installed Windows smoke.
6. **Alternate CI:** `azure-pipelines-nox-v16.yml` already exists; Azure migration document explicitly states `ACTUAL AZURE EXECUTION: NOT_RUN` and project/agent connection not verified. Reuse instead of creating another pipeline only if account owner authorizes CI access.
7. **V16 R1 blockers:** approved HOME/MENU/WORK and each persona SHA, 10+10+10 Rule1 pixel/motion checks, actual UI↔native ACK for every claimed function, Model Center/Ollama streaming/STOP, history/SQLite ACL, RAG/LoRA, GPU, voice/calls, install/update/rollback, E07 same SHA. SOURCE exists for many, installed verification NOT ESTABLISHED.
8. **Full-source-coverage clause SCG-01..07:** metadata discovery ≠ indexed/read/verified. No project-wide 100% coverage claim based on PR file listings.

**Current actionable owner gate:** I0 uses exact frozen PR #162 and already-approved original resources, resumes a permitted Windows runner (Azure fallback only if connected/authorized), builds one native NSIS candidate and supplies Setup/EXE SHA; #2 independently E07 tests that same BuildID. OIE stays an optional additive source donor until native route contract authorization; never block existing Release 1 with a standalone future studio.

**Status:** OIE SOURCE REGRESSION PASS; HOST ROUTE UNKNOWN/UNBOUND; WINDOWS HOLD; E07 NOT_RUN; RELEASE HOLD. No fake percentages.
