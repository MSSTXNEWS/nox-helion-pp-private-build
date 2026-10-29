# NOX V16 · ONEHOST Windows CI migration: Azure Pipelines (2026-10-28)

## Purpose and truth status
- Existing unified source candidate: [PR #162](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/pull/162), use its **current HEAD**, not frozen historic main as operational base.
- Canonical alternative Windows pipeline: [azure-pipelines-nox-v16.yml](../../azure-pipelines-nox-v16.yml). This is not a new NOX product, owner fork, database, or staging tree. It uses the existing private_build.ps1 and E06 ONEHOST/NSIS/immutable E07 handoff.
- **ACTUAL AZURE EXECUTION: NOT_RUN**. An external Azure DevOps project/service connection has not been verified. Microsoft-hosted Windows capacity is not verified.
- **RELEASE: HOLD**. Expected source SHA or Azure YAML presence is NOT evidence of verified 729 source files, binary BuildID, installed Windows runtime, GPU, voice, or E07 approval.
- Keep original GitHub Actions workflows as preserved diagnostic CI; do not remove them, old PRs, source parts, approved D02 assets, WOW001-200, eight CoreID, five Persona or user data. No forced push to main.

## Evidence: why alternative needed
- Recent GitHub Actions on the unified branch include source audit run 40706309484 and several Windows gates that concluded failure with `jobs[].steps = null`, and no job logs. These are pre-step failures; root cause is **UNCONFIRMED** (runner provisioning/permissions/billing/policy are hypotheses, not findings).
- Earlier workflow 40615290470 executed 9 and 14 steps successfully. Therefore a regression in runner allocation/scheduling/entitlement should be investigated before blaming app code.
- DO NOT claim the Azure route has fixed a GitHub organizational limitation. Different provider requires its own account authorization and Windows agent capacity.

## Activate the fallback without exposing the private repo
1. In an owned Azure DevOps organization create/use a **private project**; owner authorizes project access explicitly.
2. Create a YAML Pipeline from the existing **private GitHub repository** `MSSTXNEWS/nox-helion-pp-private-build`; grant the narrow GitHub connection scope only after owner review. Do not paste GitHub personal access tokens in YAML or chat.
3. Choose the existing branch `integration/nox-v16-unified-candidate-20261028-r01`, the exact file `azure-pipelines-nox-v16.yml`, and make a **manual pipeline run**. Check Azure's Windows hosted parallel-job entitlement; if no Windows host available, request a permitted agent/grant or use an authorized Windows self-hosted agent.
4. Record the exact Azure run URL, `Build.SourceVersion`, Windows image, start/end timestamps, each job/step log, and produced artifact hashes. If checkout fails, inspect private GitHub authorization; if no agent starts, inspect hosted capacity. This is EXTERNAL_INFRA_HOLD, not a source regression.
5. For each run require the original 60,364,346-byte archive SHA-256 `ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a`, **individually** verify 3 part size/blob pins and all 729 contained members. Exact measured receipt only; no fabricated SHA or ZIP counts.
6. Run original `private_build.ps1`, pinned P01 R11 staging, approved Creative/WOW source, WPF/WebView2 and the **existing** NSIS installer, then `Emit-E07ImmutableHandoff.ps1`. Do not bypass source failure, model rights, consent, trust or rollback to get a green pipeline.
7. Inspect binary Setup and WPF EXE actual SHA-256, exact source commit, `E07_BUILT_HANDOFF.json` and receipts; artifact is **BUILD_ONLY**. Do not publish a public binary or expose archive parts/secrets.
8. Send one frozen BuildID + Setup/EXE sha to **manual #3 E07**, who independently installs, checks update/rollback, validates the same binary on Windows and executes 10 native E2E scenarios. Change to source or executable => new build and new E07 checks.

## Non-negotiable source/CI inventory
- `source_00.part` 20,971,520 bytes, `source_01.part` 20,971,520 bytes, `source_02.part` 18,421,306 bytes: these are *expected claims* until actual source read.
- `coordination/e06/verify_original_729_source.py`: original three-part pin receipt, `coordination/source-lock/verify_original_archive.py`: inner 729 member namespace/hash receipt.
- `coordination/e06/stage_p01.py`, `integrations/creative/stage_creative.py`, `integrations/wow200/stage_wow200.py`.
- `coordination/e06/build_onehost_installer.ps1`, `coordination/e06/Emit-E07ImmutableHandoff.ps1`.
- `azure-pipelines-nox-v16.yml` (manual only), GitHub Actions left in place.
- GitHub issue [#177](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/issues/177) = manual 3 owners + fifteen existing automatic tasks, groups W1 :35, W2 :45, W3 :55, W4 :05, W5 :15 Europe/Moscow.

## Accountable owners and status gates
- Manual #1: only final BuildID/source graph and release candidate; exact owner preimage SHA and CAS against current PR162; Azure project connection requires account owner's authorization.
- Manual #2: source owner defects and reproducible tests; no second host/downloader/DB.
- Manual #3: independent E07 same-EXE QA, no privileged product edits.
- W1–W5 15 automation IDs remain active/unchanged schedule; merely learn this single CI reference and output receipts, without spinning up 15 competing builds.
- Reporting states: `SOURCE_CANDIDATE` / `COMPONENT_VERIFIED` / `AZURE_CI_CONFIG_SAVED` / `AZURE_RUN_NOT_RUN` / `WINDOWS_BUILT_HOLD` / `WINDOWS_INSTALLED_HOLD` / `E07_0_OF_10` / `RELEASE_HOLD`. Preserve older completed TaskID separately from release acceptance.

## Rollback and no-loss
- Original pre-change prompts preserved on branch `coordination/nox-v16-noloss-snapshot-20261028-c01` under `coordination/task-archive/NOX_V16_PRE_AZURE_MIGRATION_15_PROMPTS_20261028.json`.
- Do not change current GitHub default branch or force-merge PR162. Owner must compare full before/after tree and pass E07.
