NOX HELION V16 — GITLAB FREE MIGRATION / NO-LOSS / 2026-10-28

STATUS: PREPARED ON GITHUB ONLY. GitLab repository has NOT been created or imported by this assistant.
DO NOT DELETE THE ORIGINAL PRIVATE GITHUB REPOSITORY OR DISABLE EXISTING 15 CHATGPT AUTOMATIONS
UNTIL GITLAB BRANCHES, LFS, ISSUES, MERGE REQUESTS AND RAW ORIGINAL SOURCE ARE READ BACK.

Source: https://github.com/MSSTXNEWS/nox-helion-pp-private-build
Import destination: https://gitlab.com/projects/new#import_project
Choose GitHub importer -> Authorize with GitHub -> the single PRIVATE repository
MSSTXNEWS/nox-helion-pp-private-build -> destination PRIVATE.
Under optional import selections, include Markdown attachments and check collaborators carefully.
Do not use GitLab import-all: the task is only NOX and preservation is critical.
Choose a new project name if needed, e.g. nox-helion-pp-private-build.
GitLab Free currently includes 10 GiB repo/LFS and 400 compute-minutes per month.
Original repository about 95 MiB metadata, well below 10 GiB, but GitLab quotas
must be measured on the imported project. GitLab SaaS hosted Windows beta runner:
saas-windows-medium-amd64, Windows Server 2022, 2 vCPU/7.5GiB.
Windows runner has compute factor 1 (beta); no stability guarantee. Some GitLab
accounts require card or phone verification for hosted CI even on Free tier.
Fallback: register your own GitLab runner on an existing Windows PC with tag
nox-windows-local. Set NOX_WINDOWS_RUNNER_TAG=nox-windows-local in Run pipeline;
this runner costs no GitLab hosted compute minutes, but uses your local PC.

Authoritative integration branch in GitHub:
integration/nox-v16-unified-candidate-20261028-r01 (MOVING; NOT RELEASE).
The import snapshot and manually runnable GitLab CI live in:
migration/nox-v16-gitlab-free-20261028-r01 (FIXED SOURCE COPY FROM PR162).
The original Azure source remains at azure-pipelines-nox-v16.yml.
GitLab .gitlab-ci.yml runs ONLY after a manual Run pipeline with variable
NOX_APPROVE_WINDOWS_BUILD=YES and branch migration/nox-v16-gitlab-free-20261028-r01.
No automatic pipelines, imports, pull requests, billing, downloads or paid tiers.
This GitLab runner reuses the FOUR original canonical PowerShell Azure stages,
with GitLab environment substitutions, rather than maintaining two WPF/NSIS builders.
Artifacts: private GitLab job artifact, seven-day expiry; diagnostic only.
Do not label a diagnostic Setup as production, and do not upload raw original
archive, model weights or user profile into public releases.

MINIMUM NO-LOSS ACCEPTANCE AFTER IMPORT (must be real, not inferred):
1. Imported repository PRIVATE; confirm all original branches, tags, Git history.
2. Compare exact Git object SHA of original source_00.part/source_01.part/
   source_02.part (expected: e484e10d7b4ec9badeaae4c9d3a7e3aee5faa16b,
   7853cb43ff4ba0ed3023e8d794d8222eedea56a6,
   cbd9deb30860737f15e2adbaef2eaaf5d607a0de).
3. Combined original ZIP exactly 60,364,346 bytes / SHA256
   ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a.
   Verify all 729 original members with both existing E06 validators, not just Git metadata.
4. Compare saved D02/WOW001-200 / 8 CoreID / 5 Persona files and owner receipts
   to the source snapshot. Compare Git histories (commit hashes) and commit counts.
5. Confirm imported GitHub issues, PR discussions/comments; optional attachments are
   not imported by default and must be explicitly selected.
6. GitHub Actions workflows, Actions run logs/artifacts, GitHub secrets,
   GitHub app installations, scheduled GitHub workflows and ChatGPT's 15
   automations DO NOT magically migrate into GitLab. Keep source GitHub as
   read-only rollback until independently archived or reconfigured.
7. For CI, manually run GitLab -> Build -> Pipelines -> Run pipeline -> select
   migration branch -> NOX_APPROVE_WINDOWS_BUILD=YES -> start.
   Optional NOX_WINDOWS_RUNNER_TAG=nox-windows-local for your private Windows PC.
8. Validate same SHA, SourceLock/729, actual WPF+NSIS Setup, payload manifest,
   BuildID+Setup/EXE hashes; then independent E07 QA01..QA10 on installed Windows.
   Release acceptance remains HOLD until all ten pass.

MIGRATION LIMITATION: No GitLab account or OAuth integration is connected to the
current ChatGPT toolset, so the actual cross-provider import and Windows runner
registration require user authorization in GitLab. This branch is a prepared,
private, non-destructive migration package and must not be called complete transfer.

GitLab import docs: https://docs.gitlab.com/user/project/import/github/
GitLab Windows hosted beta: https://docs.gitlab.com/ci/runners/hosted_runners/windows/
GitLab compute: https://docs.gitlab.com/ci/pipelines/compute_minutes/
