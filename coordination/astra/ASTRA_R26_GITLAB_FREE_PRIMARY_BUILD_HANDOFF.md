# NOX V16 · OWNER-CHOSEN PRIMARY WINDOWS BUILD: GITLAB FREE (R26, 2026-10-29)

## CONFIRMED OWNER DECISION, NOT AN AZURE OR GITHUB ACTIONS RECOMMENDATION

User chose **GitLab Free** as the PRIMARY Windows build/CI integration on 2026-10-28, and the project import and at least one Windows CI launch are supported by earlier owner screenshots and existing GitHub source receipt. All earlier fallback mentions of Azure, GitHub Actions, old Release1 or smoke-runner are historical, NOT the chosen primary.

- Actual chosen PRIVATE GitLab project URL: `https://gitlab.com/s-grouptwet/nox-helion-pp-private-build`
- Actual GitLab project path: `s-grouptwet/nox-helion-pp-private-build`
- Initial GitLab migration branch: `migration/nox-v16-gitlab-free-20261028-r01` (historical snapshot; do not assume latest Astra source is already synced)
- First actual pipeline recorded: `#3000422727`; Windows job `#17549234693`, runner tag `saas-windows-medium-amd64` (Windows hosted beta).
- Recorded result: Windows CI started, failed on **P02 overdeep nested JSON** protocol test. NO accepted Windows Setup/EXE/E07. Historical source fix donor PR #203 / commit `07e1a05752685c59b55b2ad49f4ef7701e81333e`; check actual current P02 code before duplicating.
- Current ChatGPT connectors in this context can READ/WRITE private GitHub and Google Drive but **DO NOT provide authenticated direct GitLab access**. Therefore a past pipeline run is confirmed from earlier owner-provided evidence, but current LIVE GitLab branch SHA, project file tree, CI output and credentials are **NOT independently reread here**. Astra must confirm with authenticated GitLab client/account before final source handoff; DO NOT claim current live equality from the GitHub mirror.

## EXACT VERIFIED BUILD CONFIGURATION SOURCE PATHS
The following files exist in GitHub branch `migration/nox-v16-gitlab-free-20261028-r01`, and are the vetted configuration/source scaffold for the GitLab project after verified sync:

1. `.gitlab-ci.yml` (GitLab CI entry point, Windows runner tag, manual-only consent gate).
2. `coordination/e06/gitlab_windows_entrypoint.ps1` (PowerShell Windows job controller, hard-pins old branch and passes GitLab environment to four source stages).
3. `tests/e06/test_gitlab_free_source_gate.py` (source-only tests of explicit CI gate).
4. `coordination/migration/GITLAB_FREE_MIGRATION_NOLOSS_20261028.md` (migration source history, cautions, validated asset/import evidence).
5. `azure-pipelines-nox-v16.yml` (existing FOUR PowerShell stage **definitions**, currently reused by the GitLab adapter; this is not an active Azure destination).
6. `coordination/e06/verify_original_729_source.py` and `coordination/source-lock/verify_original_archive.py` (3-part ZIP SHA256 + original 729 members source checks).
7. `private_build.ps1` (legacy pinned original source builder invoked from one of the four stages, NOT to be run during source development).
8. `coordination/e06/build_onehost_installer.ps1` (one WPF/WebView2 + native Python/NSIS diagnostic builder, not an Astra coding command).
9. `coordination/e06/Emit-E07ImmutableHandoff.ps1` (immutable Windows BuildID+SHA handoff).
10. GitLab artifacts path: `work/gitlab-artifacts/` (from YAML); generated receipt `work/gitlab-artifacts/GITLAB_NOX_WINDOWS_RUN_RECEIPT.json`; E07 handoff source path `work/e06/azure-onehost-diagnostic/E07_BUILT_HANDOFF.json` is historical directory naming used by the reused stage, **not Azure provider execution**.

**Original GitHub migration configuration exact Git blobs verified 2026-10-29:**
- `.gitlab-ci.yml`: `86234bbb059d8fd9edaf21b0561e99cff1bb6714`
- `coordination/e06/gitlab_windows_entrypoint.ps1`: `a330977156c49aab0c433978b0d924549c5e2421`
- `tests/e06/test_gitlab_free_source_gate.py`: `88d84097d752d5dfb53329215677dccf5454ed34`
- `coordination/migration/GITLAB_FREE_MIGRATION_NOLOSS_20261028.md`: `cb19790dd5291672d7a86fc2e2930a71698d26a3`

The imported GitLab project may not have all these GitHub migration-branch revisions: **verify source SHA in GitLab before calling them present there**. The diagnostic entrypoint requires exactly branch `migration/nox-v16-gitlab-free-20261028-r01` and approval variable `NOX_APPROVE_WINDOWS_BUILD=YES` for a MANUAL web/API run. Thus a final new source branch won't build safely without a separately reviewed future CI adjustment. This is a **future integration task** only.

## CROSS-PROVIDER DRIFT VERIFIED IN SOURCE GIT (NOT LIVE GITLAB)
On GitHub in current turn:
- migration branch `migration/nox-v16-gitlab-free-20261028-r01` vs Astra working branch `astra/v16-code-complete-source-only-20261029`: diverged, **101** commits ahead and **21** behind (relative to migration base), 163 file differences reported in compare. This is source-Git history relation, NOT a measurement of live GitLab state.
- migration branch vs `integration/nox-v16-unified-candidate-20261028-r01` draft PR #162: diverged, **88** ahead / **21** behind, 154 differences.
- Never force-push, reimport the project, silently replace GitLab source with old migration snapshot or auto-merge historical diverged branches. Preserve unique 21 migration-side commits and reconcile only verified non-duplicated code during the later single SOURCE_FREEZE handoff.
- Astra's starting source SHA is `817bb4146db0a2c79407d249d54fdeeb22261bb6` plus Astra-only instruction/manifest commits; this is NOT current GitLab pipeline build SHA. GitLab last known pipeline #3000422727 used earlier migration source, failed P02.

**Проверка исторических исходников GitLab vs Astra:** прочитай `coordination/astra/ASTRA_R26_GITLAB_VS_ASTRA_SOURCE_DRIFT_20261029.json` — инвентаризованы 27 уникальных файлов миграции, 41 изменённый общий файл, защищённые оригинальные 3 source_0*.part. Ветка GitLab не равна Astra. Не синхронизировать или переписывать GitLab до полного SOURCE_CODE_COMPLETE и отдельной независимой интеграции.

## SOURCE FIRST — EXACT REQUIRED HANDOFF SEQUENCE
Astra SOLO agents A01..A10 on GitHub `astra/v16-code-complete-source-only-20261029` finish 100% V15/V16 **source implementation** and focused source regressions; preserve original 56 §33 consolidated rules, original 3 raw archive parts/729 members, 968 baseline Git blobs, D02/WOW200, 8 CoreIDs, 5 Personas, 50+50 routes, Voice RU↔ES, RAG/LoRA/GPU, SPACE, user data, earlier DONE. Google Drive source journal read/write every actual run, errors and self-improvement.
**DO NOT run GitLab CI, Azure, Windows build, NSIS, diagnostic EXE or any premature cross-owner integration while source still changes**.

After `CODE_COMPLETE_CANDIDATE` and independent source no-loss audit, a **different authorized integration owner**:
1. Select and pin ONE exact frozen Astra source commit/tree (and all approved independent donor changes); verify original 729 physical ZIP and all V15/V16 TaskID evidence.
2. Inspect current authenticated GitLab project's PRIVATE clone and selected branch actual HEAD, not historical memory; compare unique GitLab migration changes, no-loss and license/permissions.
3. Non-destructively synchronize final accepted source and maintained GitLab CI scaffold, with exact pinned Git commit for GitLab CI and reviewed branch allowlist (migration branch is hardcoded in PowerShell now); no force push or reimport. Keep GitHub as preserved history/rollback.
4. Only THEN owner explicitly authorizes one final GitLab Free Windows pipeline; no automatic push builds, explicit `NOX_APPROVE_WINDOWS_BUILD=YES`, exact source commit pinned, available runner, safe software licenses, no surprise charge.
5. Independent installed Windows E07 10/10 must check exactly one immutable binary SHA/BuildID. Until then RELEASE=HOLD, NOT GitLab=accepted.

**Astra's deliverable is exclusively SOURCE CODE + TaskID/sha/test + no-loss receipts for the separate GitLab handoff.**

## Prompt precedence
This R26 supersedes the prior mini prompt wording "build integration unknown / owner will later choose it": **owner already chose GitLab Free**. Azure and old separate repositories are historical alternatives. It does NOT change the current ban on intermediate builds, nor prove current GitLab client access.
