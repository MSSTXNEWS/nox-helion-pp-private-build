# NOX HELION V21 · ПОЛНАЯ СВЕРКА V16 §22 / WOW 10+10+10 / ФУНКЦИИ / ПРОВЕРКИ

Дата: 2026-11-10 · источник: [V16](https://docs.google.com/document/d/11EM0qW3PJN0WqV8Euc1A2X4c0UukHiVq_0WfaLYVYpc/edit) + [E06 report](https://docs.google.com/document/d/17scXv-pnI0hJYAw1I706cxc3lybsO23yue1AIYsmNU4/edit), [E06 lessons](https://docs.google.com/document/d/14FXmVrgd7rCR7mDKDfJ-1hpbU6DNI_Znqk1af_6BrDQ/edit), [MASTER](https://docs.google.com/document/d/1evk2XhCAT_zY97MmMunTCCHXViSlnTshf2EzfKYWR98/edit).

**Source of truth:** GitHub [PR #241](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/pull/241), working branch `fix/home-v16-cinematic-contract-20261110`, candidate source directory `web-home/candidates/2026-11-10-v16-cinema/`. PR is DRAFT, not merged, production not promoted. This report is an audit, not a completed-work claim.

## Important source conflicts that must not be hidden

- The newer V16 §22.2 R09, §22.8, §23.1 says **HOME = central HELION + exactly 8 CoreID, Persona videos only on secondary screens**. The V20 director overlay adds 5 Persona cards on HOME. This is **CONFIRMED DESIGN-CONTRACT CONFLICT**; do not delete Persona assets, transfer their UI to secondary Persona Hub with original IDs/history instead. Check any newer explicit owner change before changing visual source.
- V16 originally specified one final **Windows EXE**, but this PR is a **WEB candidate**, deliberately preserving original native backend. An accepted WEB preview does not mean V16 EXE acceptance. The latest explicit user request to finish WEB takes priority for this PR, not permission to remove native deliverables.
- The user explicitly requires **no visible dropdowns and no fake/inert active buttons**. Current `nox-global-wow-v18.js/css` converts native select options into real button groups and emits native input/change events. On [browser QA of previous source SHA](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/42853287830), zero visible dropdowns and 10/10 page structural checks passed. **Not a proof every button is wired**, and a disabled button with no backend must not be advertised as working.
- `50/50 npm archives downloaded` != `50 live libraries` != `50 working functions`. The baseline WEB has 26 pinned **files** (including license text and associated assets), fewer actual runtime engines. Never inflate percentages by treating downloaded tarballs or resources as completed integration.
- Source verification, functional click test, actual hardware GPU, Windows integration, accepted release are distinct.

## WOW 10+10+10: exact V16 §22.2–22.4 criteria and current state

Legend: **SOURCE** = candidate implementation/assets present; **PARTIAL** = some related source and limited browser evidence; **HOLD** = no acceptance evidence for whole criterion. **ACCEPTED** requires independent same-BuildID physical QA; none marked accepted here.

| ID | Canonical required effect | Source / current evidence | Status and what remains |
|---|---|---|---|
| R01 | PBR-like obsidian/metal/glass/stone | `industrial-assets.mjs`, `assets/nox-approved` and 14 pinned PBR/HDRI assets | PARTIAL — side-by-side physical screenshots, all material variants |
| R02 | Roughness/metalness reacts correctly to moving light | Metal012 roughness/normal/metalness + Three.js renderer | PARTIAL — animated lighting and real shader observation |
| R03 | Plausible reflections/contact shadows/spatial harmony | Existing WebGL and shaders | HOLD — visual/physical proof of shadow/occlusion/reflections |
| R04 | Atmospheric depth and light rays or approved layer approximation | `industrial-effects.mjs`, `nox-home-flow.js` | PARTIAL — cinematic light depth QA |
| R05 | Local heat distortion near hot surfaces only | `industrial-effects.mjs` | HOLD — effect locality and no global text blur |
| R06 | Microtextures, scratches, dust and lit edges | ambientCG maps, CSS materials | PARTIAL — sample physical screenshots |
| R07 | Genuine depth/parallax, not zoomed wallpaper | D02 WebGL + `physical-worlds-v7.mjs` | PARTIAL — test perspective/camera with rotating worlds |
| R08 | Orbital inertia, gentle repulsion, non-overlap 8 cores | `nox-owner-fidelity-v21.js`, orbit/physical worlds | HOLD — ≥5 min recorded collision and trajectory QA |
| R09 | Approved living Persona on secondary screens; **none on HOME** | Five static portrait assets and current V20 HOME cards | **CONTRACT CONFLICT** — move cards to Persona Hub; live approved video and source ID review |
| R10 | Film exposure/glints without losing legibility | shared cinematic CSS and WebGL | PARTIAL — luminance/contrast and text readability QA |
| W01 | Continuous scene, controlled visual hierarchy | D02, flow animations and Reduced Motion | PARTIAL — 5+ min active/idle state QA |
| W02 | Exactly 8 CoreID coexist naturally | 8 CoreID elements in prior Chromium 7/7 viewport source | PARTIAL — collisions, all 8 functions and event state |
| W03 | Flow beneath obsidian shell and independent corona | D02 restored by locked SHA | PARTIAL — verify actual corona animation on physical GPU |
| W04 | Objects respond to each other/selection beyond hover | orbital/GSAP helper | HOLD — interaction tests beyond simple CSS hover |
| W05 | Approved Persona video/look/breathing on secondary pages | Five approved static portraits only | HOLD — video assets, timelines and secondary UI |
| W06 | Actual backend events drive light and physics; idle not training | `nox-cinematic-health.js`, event consumer scaffolding | HOLD — connect events.v3 proof end-to-end |
| W07 | MENU as physical destination instead of simple drawer | Current navigation/director overlay | HOLD — proper transition and real route acceptance |
| W08 | Section covers are living mini-scenes reusing one master environment | Shared CSS across 10 routes | HOLD — per-page live scene rather than just shared styling |
| W09 | Material/volumetric functional buttons and secondary surfaces | `nox-global-wow-v18.css/js`, `nox-glass-*.css/mjs` | PARTIAL — click-action census, pressed/focus/keyboard/a11y on every route |
| W10 | Continuous HOME → core/menu → section → back, context preserved | Existing real links to ten pages | HOLD — selection/session persistence through browser and Windows |
| C01 | Instant readable establishing shot HELION+8 | D02 in Chromium 7/7 source screenshots | PARTIAL — art-direction acceptance on real GPU |
| C02 | Slow camera drift/parallax idle | GSAP / flow and original renderer | PARTIAL — timing/quality observation |
| C03 | Rack-focus selected Core/function/Persona outside HOME | Existing focus/visual helper | HOLD — camera rig acceptance and secondary Persona screen |
| C04 | Smooth push-in/fly-through transitions | existing routing and animation helpers | HOLD — transition runtime, no abrupt document replacement |
| C05 | Orbital MENU reveal with coordinates restored | `nox-owner-director-v20.js`, `nox-orbit-original.js` | HOLD — camera position and navigation round trip |
| C06 | Rays/smoke/occlusion depth but no button obstruction | existing effects and composition | PARTIAL — physical readability and occlusion QA |
| C07 | Renderer-based filmic tonemap/bloom/HDR, not on text | Three postprocessing vendor and D02 | HOLD — one composition chain and GPU-budget QA |
| C08 | Kinetic legible typography/specular sweep | shared WOW CSS | PARTIAL — keyboard/readability/reduced motion QA |
| C09 | Spatial UI sounds opt-in, muted by default, full STOP | sound candidates only | HOLD — explicit consent, mute/volume tests |
| C10 | Seamless reverse transition HOME and preserved panels | current route links | HOLD — real state persistence and reverse motion |

**WOW assessment:** 30/30 **tracked**, 0/30 independently Windows **ACCEPTED**; do not translate source presence into a product completion percentage. Source/implementation status should be checked separately for each row against the current HEAD and verified physical SHA.

## Real functions and buttons — no dropdown/no inert active controls

| Family | What exists in this PR / baseline | Required end-to-end acceptance |
|---|---|---|
| D02/HOME | 14 original orbital/theme/mode controls, 8 CoreID, original D02, five image assets | Exactly 8 CoreID HOME; all 14 switches actual state; 5 themes incl black-gold; 4 lighting scenarios; no overlaps at 7 viewports; no fake telemetry |
| Navigation and command center | Ten base HTML routes, `nox-global-wow-v18.js` button converter, `nox-universe-v19.js` service buttons | Every enabled button has route/mutation/dialog and observable result; no hidden dropdowns; Ctrl+K; back, selected state, no placeholder link |
| Cinema | Video URL/local file, Shaka, subtitles, resume, fullscreen in `nox-universe-v19.js`; existing `cinema.html` | Actual MP4/WebM/HLS in browser, VTT, seek/resume; CORS/DRM honest hold; projector requires host device |
| Books & documents | PDF.js, worker, epub.js, TXT and existing `memory.html` reader | Real PDF + EPUB pagination/bookmarks, TXT, OCR where available; permission and sandbox tests |
| Gallery | PhotoSwipe upload and lightbox | Open **and close** real modal, pan/zoom/keyboard, release objectURLs, then next button must still work |
| Calendar | FullCalendar + browser-local storage, add/delete | Click create/delete/reload persisted event; no fake Google/Microsoft sync, OAuth is separate |
| Atmosphere FX | tsParticles Slim MAX/BALANCED/ECO/STOP | Real canvas start/stop, freed resources, hidden tab/reduced-motion safety, D02 unaffected |
| Weather/maps | Leaflet + Open-Meteo/OSM | Real user-selected city, response and tiles, copyright/usage/429/CORS |
| News/search | HN feed, RSS in browser, Fuse catalog | Verified RSS sources/date, CORS fallback, 130 catalog entries linked to *actual* actions rather than status-only toast |
| Notifications | local center and permission diagnostics | True service worker + authenticated owner push endpoint, subscription & device delivery, disabled if missing |
| Voice/translation | existing NOX voice references, browser feature buttons | Real RU/ES ASR/TTS, silence/STOP/barge-in; no mock prerecorded voice |
| Memory/graph | existing S03 and `memory.html` | Read/write/delete/rollback with real SQLite/host and source SHA, no invented relation graph |
| Projects/installer/models | existing native routes | Actual Windows host bridge/IPC actions; no claim based on static page links |
| Training/RunPod | `nox-progress-core.mjs`, read-only weight auditor, SYSTEM/TRAINING proof panel | Real trainer_state+full weight bytes, teacher provenance, baseline eval, Windows readback and STOP |
| Media/specials | candidates include chart, wavesurfer, video.js, maps, push SDK | Only selected compatible engine per responsibility; document license, version and real handler, no parallel renderer |

**Source audit:** Current built static candidate has ten HTML pages with 74 inline buttons total (10 HOME, 23 CHAT, 8 CINEMA, 0 INSTALL, 1 MODELS, 20 MEMORY, 0 PROJECTS, 0 SETTINGS, 2 SYSTEM, 10 TRAINING), before dynamically created modules. The native HTML `select` count is zero in those ten pages; dynamic converters still need recheck. No invalid blank or `href="#"` navigation anchors found in the static inspection. **Zero native buttons on INSTALL/PROJECTS/SETTINGS does not prove those routes have functional actions**: they may use JS-created elements/links or be nonfunctional. Active-button click census and behavior receipts are still required; none may be falsely labelled accepted. Static TODO/HOLD strings do not by themselves prove a stub, but the catalog's planned actions should remain visibly non-actionable until wired.

## CI and sourced build evidence

- [Previous fully green Chromium acceptance](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/42853287830) for earlier SHA: 10/10 page routes, 7/7 viewports, real Calendar/Gallery/FX scenarios — source-specific; not current HEAD.
- [Current SHA98 run](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/42867343440): source-syntax PASS, vendor intake PASS, ten-page build PASS, 261 references PASS; **Chromium FAIL** despite 7/7 viewports and 10/10 pages because after PhotoSwipe test, clicking the next tab `Эффекты` timed out; new change in `tools/browser-acceptance.mjs` closes the PhotoSwipe dialog and waits for teardown. Must rerun and verify the exact next SHA, not retroactively mark PASS.
- CircleCI context on SHA98 [ERROR](https://app.circleci.com/pipelines/gh/MSSTXNEWS/nox-helion-pp-private-build/3502); do not ignore.
- WEB full source staging 26 runtime-vendor files in current source target, 24 previously built, each receipt SHA-256; original D02 and HOME locked, 173 pinned baseline paths. Physical NVIDIA/AMD WebGL QA and independent Windows acceptance NOT performed.
- Headless Playwright on SwiftShader is not real GPU acceptance; local RunPod A40 GPU % is not student distillation progress.

## Where to obtain the canonical assets and instructions (not interchangeable)

1. [V16 full requirements](https://docs.google.com/document/d/11EM0qW3PJN0WqV8Euc1A2X4c0UukHiVq_0WfaLYVYpc/edit) — §22 exact 10+10+10, §23 working buttons, project requirements; §7 native build budget and 1–5 / 6 / 7 acceptance.
2. [WOW LIVING UI V3](https://drive.google.com/file/d/1nkzWT2e3Va5_cJEtZWWEqAnx4Xn9D_Mi/view) — master rig/physical motion / materials (do not substitute unverified historical demo).
3. [MAX WOW VIDEO / full-screen production](https://drive.google.com/file/d/1UdBW99SXGpgMadaVCsRSTynwuN8unVBypgmh4R8lvCA/view) — MA-01…MA-15, S01…S42 concepts. 60 engines / 120 presets are planned quantities, **not** verified runtime files.
4. [Original design/layout all screens](https://drive.google.com/file/d/1Hp_eDHU_-fW8w8rDHSSmy-cMxD9ScAXw/view) — approved concept. Source screenshots in `assets/nox-owner-approved` after SHA validation.
5. [E06 report](https://docs.google.com/document/d/17scXv-pnI0hJYAw1I706cxc3lybsO23yue1AIYsmNU4/edit), [E06 lessons](https://docs.google.com/document/d/14FXmVrgd7rCR7mDKDfJ-1hpbU6DNI_Znqk1af_6BrDQ/edit) and [MASTER journal](https://docs.google.com/document/d/1evk2XhCAT_zY97MmMunTCCHXViSlnTshf2EzfKYWR98/edit) — before merge or release; enforce source SHA / RunID alignment.
6. [Approved web source directory](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/tree/fix/home-v16-cinematic-contract-20261110/web-home/candidates/2026-11-10-v16-cinema) — PR #241 exact patches and scripts. Original 173 files restorable only with `tools/restore-pinned-baseline.mjs` and the three SHA manifests.
7. [All 50 npm package sources](https://drive.google.com/drive/folders/1LqUj69xXto7lg8bJvn_pLfQiIZ_rL1Kx) — multipart zip (source inventory, not 50 browser features). Exact local runtime dependencies are `nox-install-extra-v19.mjs` and `vendor/nox-extra/NOX-EXTRA-ASSETS-RECEIPT.json` in successful build output.
8. [Poly Haven](https://polyhaven.com/), [ambientCG](https://ambientcg.com/), [Three.js](https://threejs.org/), [GSAP](https://gsap.com/), [FullCalendar](https://fullcalendar.io/docs), [PhotoSwipe](https://photoswipe.com/), [PDF.js](https://mozilla.github.io/pdf.js/), [Open-Meteo](https://open-meteo.com/) — source licenses and versions must be pinned; access does not imply installation.
9. RunPod A40 active `cu1zrw3apt5zt0` has global volume `cmw9c11rb000007l6dr6d0eu9` at `/workspace`; requires authorized filesystem execution to attest real full student checkpoints. RUNNING only proves compute; do not launch or stop another Pod based on this report.
10. Windows native main / source bundles and R8/PR #162 remain a **separate** system of record; do not replace `MainWindow.xaml.cs`, native SQLite or installer from PR #241 without whole-tree no-loss and independent same-SHA E07 acceptance.

## Ordered closure / release blockers

P0: correct the *current* gallery→FX navigation defect and rerun browser QA on same SHA. P0: count and exercise **all enabled buttons**, not just 5 feature smoke tests; deliberate HOLD/unavailable must not be a fake enabled action. P0: reconcile V16 HOME-only-HELION+8 against earlier five HOME Persona cards. P0: V16 §22 30 independent cinematic criteria with reproducible before/after screenshots and physical 7 viewport acceptance, five themes, four light scenes, 14 controls, multi-minute motion and actual GPU. P0: existing host bridge/one NOX chat/STOP/S03/SQLite safety acceptance. P0: RunPod actual full weight hash/steps/teacher provenance, Windows checkpoint readback. P0: full V16 owner 1–5 ledger/progress based on TaskID criteria and SHA, one serialized integrator #6, independent #7 acceptance. P1: media PDF/EPUB/HLS, live news/weather/currency, push/OAuth, voice RU↔ES, memory graph and native installers/project routes; test each separately with its approved origin and permission. P1: release notes/license clearance/rollback, CircleCI CI repair and no production promotion until all gates pass.

## Post-audit fixes on this branch
- PhotoSwipe overlay navigation fix in `nox-universe-v19.js` and browser teardown in `tools/browser-acceptance.mjs`; recheck current SHA.
- Unimplemented catalog requirements now remain visible as *read-only text*, not buttons that only print HOLD; all actual route buttons remain.
- `NOX-WOW30-TRACEABILITY.json` is an exact machine-checkable R01–R10/W01–W10/C01–C10 manifest, with 14 PARTIAL source areas, 15 HOLD and one HOME Persona conflict; zero independently accepted, CI source gate rejects false acceptance.
- `nox-install-extra-v19.mjs` also pins ECharts 5.5.1 (Apache-2.0) and Lucide 0.456.0 (ISC) locally. `build-approved-assets.mjs` rewrites the old CDN script paths to same-origin files, validated by CI for all 10 pages. 26 binary/resource files (some are licenses/assets), not 26 distinct engines. Newest build/acceptance must pass before this is described as a completed integration.

**Completion contract:** Notion status, runtime button, GPU %, npm downloads, or a beautiful screenshot must never replace a signed current-source acceptance receipt. Unknown product progress = N/D; source 10/10 does not mean program 100%.
