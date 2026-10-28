# R26 SOURCE/BUILD TARGET CORRECTION — OWNER CHOSE GITLAB FREE (2026-10-28)

Primary Windows build platform **is GitLab Free**, not Azure or GitHub Actions: private `https://gitlab.com/s-grouptwet/nox-helion-pp-private-build`, historical branch `migration/nox-v16-gitlab-free-20261028-r01`; pipeline `3000422727`, Windows job `17549234693`, runner `saas-windows-medium-amd64`; P02 test failed, no EXE. GitLab CI source files (present on GitHub migration branch): `.gitlab-ci.yml` → `coordination/e06/gitlab_windows_entrypoint.ps1` → existing stage descriptions `azure-pipelines-nox-v16.yml` → original `private_build.ps1` + `coordination/e06/build_onehost_installer.ps1` → receipts under `work/gitlab-artifacts/`. GitLab branch not proven synced with current Astra; source Git histories diverge. **Read the exact verified handoff** `coordination/astra/ASTRA_R26_GITLAB_FREE_PRIMARY_BUILD_HANDOFF.md` before acting on build assumptions. Astra edits only source in its GitHub working branch; GitLab final synchronization/build belong to later separate integrator after full source completion and SourceLock. DO NOT launch GitLab CI/EXE/NSIS now. Old instructions leaving build provider "undecided" are superseded. 56 V15 rules, 10x10 agent matrix, Drive error/lesson readback remain binding.

# NOX ASTRA R24 · ABSOLUTE STARTUP CONTROL · 56 RULES + ERROR JOURNAL EVERY RUN

**HIGHEST PRIORITY:** Before writing ANY product code or creating ten subagents, read and check all **56 numbered V15 rules** from `coordination/astra/ASTRA_V16_R24_ALL_56_V15_RULES_EXACT_SECTION33.md`. Then read new/current errors from **active V16 master**, historical NOX C34 Error Journal, last E06 run report and last self-improvement lesson. After every actual launch, append fresh error status, run report and one genuine process lesson to **three active Google Docs** with CAS and verified readback; C34 is read every launch and linked by append when authorized. Failure to save = REPORT_GATE HOLD + GitHub receipt fallback, NEVER silently claim a write. Required authoritative contract with exact four Google Docs links and procedure: `coordination/astra/ASTRA_R24_MANDATORY_JOURNAL_RW_EVERY_LAUNCH.md`. This clause overrides any ambiguity in older text. Ten agents × ten passes per agent is an actual tool-spawn requirement **only where a real subagent creation tool exists**, otherwise explicitly declare unavailable and execute sequential real owner work queues—no simulated agents or fictitious 100/100. All V15 original files, D02/WOW200 and previous DONE preserved; no early builds or final integration.

# NOX HELION V16 FINAL · ASTRA SOLO · COMPLETE ALL SOURCE CODE BEFORE INTEGRATION
## Canonical source handoff — 29 October 2026

**DIRECT OWNER ORDER:** all previous manual and automatic executors will be paused by the user. From the current exact original project, ASTRA is the *only active product SOURCE developer*. Finish **100% of required V15→V16 source functions**, while preserving every original working feature, approved WOW and file. **DO NOT INTEGRATE cross-package owners or build anything.** Astra is not the final binary builder, release integrator or independent E07 controller.

### 0. Verified access / source identity

- GitHub account connector **READ + WRITE** verified in prior project chat for the PRIVATE repository `MSSTXNEWS/nox-helion-pp-private-build`; however, recheck *within your own Astra chat* before relying on it.
- V16 original source staging PR (KEEP UNCHANGED): https://github.com/MSSTXNEWS/nox-helion-pp-private-build/pull/162
- Existing PR branch: `integration/nox-v16-unified-candidate-20261028-r01`
- **Frozen initial source commit:** `817bb4146db0a2c79407d249d54fdeeb22261bb6` (verified PR162 HEAD when Astra branch created; PR162 can move later).
- **SOLE ASTRA WORK BRANCH:** `astra/v16-code-complete-source-only-20261029`, created directly from the frozen initial source commit, no historical file losses. Do all source modifications and tests here. DO NOT force-push, merge to PR162/main, or touch the separate build repos. Obtain current Astra branch HEAD before each write.
- V16 main source + V15 original Google Drive metadata verified by connector:
  - https://docs.google.com/document/d/11EM0qW3PJN0WqV8Euc1A2X4c0UukHiVq_0WfaLYVYpc/edit (especially §33 and latest §54)
  - https://drive.google.com/file/d/1CTwrMzhusE4DYKIwhOdrnNmyhOSPERbV/view
- Canonical source-only order, read first: `coordination/release/NOX_V16_R20_SOURCE_ONLY_FASTPATH_20261029.md`
- Two human roles / previous full instructions:
  - `coordination/manual_roles/NOX_V16_FINAL_TWO_MANUAL_PROMPTS_20261028.md`
  - `coordination/task-archive/NOX_V16_R20_PRE_SOURCE_ONLY_COMPACT_17_FULL_PROMPTS_20261029.json`
- Shared issue/archive of actual audits: https://github.com/MSSTXNEWS/nox-helion-pp-private-build/issues/177
- Important: 56 prior V15 rules are a *verified consolidation* (§33), not proven verbatim copy of an ancient original. Preserve all applicable functional requirements. Keep old DONE TaskID and receipts; progress requires evidence.

### 1. The BUILD INTEGRATION is DIFFERENT — DO NOT TOUCH NOW

These repos/pipelines exist but are **not Astra's source-development target**:
1. `MSSTXNEWS/nox-helion-release1-windows` = private historical Release 1 Windows staging. The present `.github/workflows/r1-two-exe.yml` is pinned to historical source archive SHA-256 `71c468ac2d0ca1086977ab2ccf68f3240bdee15a8964bb1deadab658a74c190f` and historical commit `ee4d134b6b438294b7c6ab424ba6de0a14ba72e0`; **NOT** the current V16 source. No run.
2. `MSSTXNEWS/nox-helion-windows-build` = old smoke-only runner `.github/workflows/windows-exe-smoke.yml` for an old, approved pre-release EXE. **NOT** the final V16 builder. No run.
3. The V16 alternative build pipeline **configuration only** is present in this source repo at `azure-pipelines-nox-v16.yml` and explained at `coordination/e06/AZURE_WINDOWS_CI_MIGRATION_V16_20261028.md`. External Azure DevOps organization/service connection + Windows-agent entitlement have NOT been verified; YAML != running build. No activation.
4. Historical `private_build.ps1` and `coordination/e06/build_onehost_installer.ps1` exist. No execution; preserve until later independent build owner/adaptor handoff.

**HARD GATE:** Astra SOURCE_CODE_COMPLETE → independent full SOURCE coverage → ONE SOURCE_FREEZE → separate authorized integrator merges owners once → independent SOURCE_READY → separate Windows build pipeline → independent E07 10 installed scenarios same BuildID/SHA. Never build preliminary EXE/NSIS, start diagnostic installer, trigger Windows Actions/Azure or change build repository while original code is moving. All stages after Astra code completion are separate tasks.

### 2. Exact owner source paths — audit, complete, test, preserve

**P01 · 20% UI / D02 / WOW / original functions**
- `integrations/wow200/runtime/home-scene.mjs`
- `integrations/wow200/runtime/loader.mjs`
- `integrations/wow200/stage_wow200.py` (read-only origin/pins until later freeze; do not execute a builder)
- `proposals/NOX-CINEMA-FX/nox-cinema.mjs`
- `proposals/NOX-CINEMA-FX/nox-cinema.css`
- `proposals/P01/WOW-MAX10/`
- `integrations/wow200/proposals/NOX-WOW51-100/`, `NOX-WOW101-150/`, `NOX-WOW151-200/` (under same parent `integrations/wow200/proposals/`)
- `integrations/wow200/tests/`, `integrations/wow200/runtime/*.test.mjs`.
Preserve one original HELION centre, exact 8 CoreID, 5 Persona, HOME/MENU/CORE, 200 approved WOW IDs and actual runtime effects, original user buttons/navigation handlers, Reduced Motion and 320/390/800x480/HD/4K, visual/keyboard accessibility. Do not change official images arbitrarily.

**P02 · 25% Ollama/SQLite/memory/voice/permission**
- `Packages/P02/worker-python/p02_runtime.py`
- `Packages/P02/worker-python/p02_chat_bridge.py`
- `Packages/P02/worker-python/p02_owner_route_ports.py`
- `Packages/P02/worker-python/p02_native_ingress.py`
- `Packages/P02/worker-python/p02_capabilities.py`
- `Packages/P02/worker-chat/ChatSqliteStore.cs`
- `Packages/P02/worker-chat/OllamaChatClient.cs`
- `proposals/NOX-VOICE-LAB/voice-lab.js`
- source tests: `Packages/P02/worker-python/test_*.py`, `proposals/NOX-VOICE-LAB/voice-lab.test.cjs`.
One chat LLM and SQLite, real streaming/STOP, scoped NativeSession, attachments and citations, RU↔ES ASR/LLM/TTS, Voice STOP privacy, MAESTRO and SIP ONLY with native consent/quote + actual provider. No mocked live-provider SUCCESS.

**P03 · 20% models, weights, licenses, queue**
- `Packages/P03/Source/python-host/p03_onehost_port.py`
- `Packages/P03/Admission/p03_modelcenter_gate.py`
- `Packages/P03/Source/P03.ModelCenter.Wow/index.html`
- relevant `Packages/P03/**` owner code and existing tests; inspect actual Git tree before using more paths.
24+ model families/catalogue (text/ASR/TTS/image/video/3D), pinned source/license/model-card rights/sha, GGUF import, Ollama pull, real resume/cancel/queue/progress. Do not predownload massive weights. No second downloader or installer.

**P04 · 25% memory/RAG/LoRA/GPU**
- `Packages/P04/Rag/RagService.cs`
- `Packages/P04/Rag/RagIngestionService.cs`
- `Packages/P04/Rag/RagChatContextProvider.cs`
- `Packages/P04/GpuGuardian/GpuGuardian.cs`
- `Packages/P04/train_qlora.py`
- `Packages/P04/merge_qlora_adapter.py`
- `tests/P04/`.
Source-proven RAG indexing/chunks/citations, licensing/holdout, bounded provenance, actual QLoRA/LoRA/checkpoint/STOP/PAUSE/RESUME/evaluation, GPU safety. If Nvidia GPU/weights missing, mark external hardware TEST=HOLD, do not pretend a run occurred.

**P05 · 10% telemetry/SPACE/events/mobile**
- `Packages/P05/E05/src/E05CanonicalEvents.cs`
- `Packages/P05/E05/src/E05Progress.cs`
- `Packages/P05/E05/src/E05SamplingLoop.cs`
- `Packages/P05/E05/src/E05ApprovedSpace.cs`
- `Packages/P05/E05/space/E05SpaceReadOnlyProjection.mjs`
- `Packages/P05/E05/space/E05SpaceRunErrorHistoryR15.test.mjs`
- `coordination/e06/adapters/g2_space_mobile.py` (inspect adapter contract, do not cross-owner merge).
One events.v3, factual CPU/GPU/VRAM/sensor telemetry, safe SPACE/cache/market/news/weather, mobile auth/CSRF/permission/revocation, no fake data or invented percentages.

**Preserve PACK01/PACK02**
- `proposals/NOX-PACK01-50/catalog.json`
- `proposals/NOX-PACK01-50/native_bridge.py`
- `proposals/NOX-PACK01-50/owner-binding-map.json`
- `coordination/e06_host50/CURRENT_50_TASK_LEDGER.json` (historical 36/50 and 37/50 counts are stale and mutually inconsistent; do NOT claim current missing-route total from old ledger)
- `proposals/NOX-PACK02-50/catalog.json`
- `proposals/NOX-PACK02-50/ops.mjs`
- `proposals/NOX-PACK02-50/golden.test.mjs`, `smoke.test.mjs`.
Preserve exactly 50+50 canonical function IDs. Avoid decorating buttons without real action. SOURCE routing does not establish installed runtime acceptance.

**SourceLock / non-loss originals**
- `source_00.part`, `source_01.part`, `source_02.part`
- `coordination/source-lock/verify_original_archive.py`
- `coordination/e06/verify_original_729_source.py`
- `coordination/source-lock/NOX_V16_UNIFIED_STAGING_674_FILES_20261028.json`.
Expected original combined 3-part ZIP **60,364,346 bytes** SHA-256 `ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a`, 729 inner files. Physical full SHA/729 inner hashes NOT YET independently verified as of handoff. Never delete archives; do not claim physical pass from Git metadata.

### 3. Read existing parallel patches BEFORE writing the same functionality

These are **source candidates only** and must be reviewed against your branch's latest exact file SHA, NOT blindly merged:
- D02/WOW controls + ECO: `fix/nox-v16-d02-original-controls-eco-source-r21-20261029`
- PACK02 CSV/JSON/URL safety + 26 tests: `feature/nox-v16-pack02-50-source-hardening-r22-20261029`
- P02 immutable route-map 3 owner ports + 5 tests: `feature/nox-v16-p02-three-native-ports-immutable-r22-20261029`
- Other donors: GitHub PR #204, #208, #209, #210, #211; some fixes have already been accepted in the original PR162, others are QA-only or old.
- Existing source fixes to avoid duplicating: P02 voice STOP/discard, P04 full-history EventWriter, several CreativeWorker and P03/E06 MappingProxyType fixes. Re-read current owner blobs; no stale comments as truth.

When needed, implement a correct updated source fix in your **Astra owner source** preserving all newer code and security. **NO cross-owner feature merge** until full core feature coverage.

### 4. Your immediate operating algorithm (not another report)

0. Confirm GitHub access and exact ASTRA branch HEAD. Do not modify original shared PR162/main. The fifteen scheduled automations were confirmed disabled; independent verification of other manual chat shutdown is unavailable and MUST NOT block isolated ASTRA source commits. Check per-file blob SHA immediately before modifying. Begin fixing source in this run.
1. Read original V15, actual V16 requirements, the existing P01–P05 owner ledger/last receipts, and verify the current source for already-closed requirements. Use delta not rereading giant unchanged docs every loop.
2. Create **one canonical full TaskID coverage ledger** (e.g. `coordination/astra/ASTRA_V16_TASKID_COVERAGE.json`) with *every* V15→V16 requirement mapped to existing owner path, precise gap, current status, evidence/test, SHA. Preserve historical DONE. Do not guess denominator or mark 100% by file count.
3. Choose a **shared technical root cause** affecting multiple incomplete TaskIDs, not a decorative improvement. Implement substantial actual product code in P01–P05 owner files and narrow tests. Make logical commits in Astra branch, never rewrite completed functions.
4. Run real local Python/Node/component tests where the accessible environment permits, preserving package imports and dependencies; use RED→GREEN and regression. No EXE, NSIS, Azure/GitHub Windows release workflows. Expose mock/isolated tests accurately; no fake browser/mic/GPU success.
5. Continue solving next highest-impact independent gap in this same interactive run until resources or tool budget prevent more. If blocked by external hardware, provider credentials, model rights or missing original binary bytes, record exact `EXTERNAL_BLOCKER` and do other code gaps; do not silently count them as DONE.
6. Keep each source change CAS-safe (Git pre/post blob SHA and, where verified, SHA-256), no force, no duplicate LLM/DB/event bus/downloader/GPU worker. Brief Git receipt and machine-readable progress; prior full logs preserved.
7. When **all source feature TaskIDs** have actual code + targeted tests and the coverage denominator is independently reproducible, commit `CODE_COMPLETE_CANDIDATE` manifest with all owner path Git blobs, SHA, tests and explicit untested external dependencies. This is **NOT** final `SOURCE_READY` / `INTEGRATED` / `RELEASE`. Stop before cross-owner build/integration, and handoff to the later independent source controller.

### 5. Strict evidence / final response
No "100%" without actual, mapped and tested code coverage. Report:
- exact Astra branch HEAD, URLs for commits;
- verified product TaskID newly closed vs historical DONE retained;
- touched owner paths and code changes (not plans);
- actual test command + output PASS/RED/NOT_RUN;
- remaining source gaps and `BLOCKED_EXTERNAL` items;
- status `SOURCE_CODE_COMPLETE_CANDIDATE` only when supported;
- independent integration and build = NOT_STARTED, E07 native 0/10.

**Do the work now. Do NOT ask for a new plan, do NOT redesign from scratch, do NOT start builds, and do not create a second project.**

### 6. Later handoff after Astra finishes (DO NOT execute yourself)
Independent source verifier confirms original 729/SourceLock and complete V15/V16 TaskID coverage. Then an *independent integrator* selects correct target after checking canonical V16 provenance; do NOT assume historical `nox-helion-release1-windows` R1 workflow is compatible. Azure alternative YAML exists but Azure DevOps access/Windows agent hasn't been verified. One frozen exact SHA becomes separate final Windows BuildID and E07 10/10 same SHA.
