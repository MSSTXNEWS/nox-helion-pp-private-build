# NOX Creative Studio CS5 · B01–B05 original-host adapter

**Integration source**: PR #162 exact source parent d5bcaad156b38e95ed2d15c6d96a1b08a907eba8.
**Scope**: additive patch inside integrations/creative ONLY. Not merged, not Windows E07, not owner-art-approved.

## What actually changed
- The existing trusted WPF/WebView2 action creativeInvoke and existing creative_worker.py receive three additive actions: cs5_overview, cs5_append, cs5_list.
- The original entry.js loads five_blocks.js inside the existing creative/studio.html iframe; no new top-level HOME/MENU, routes, app or ports.
- The existing Studio._project and Studio._stop_event own storage and cancellation. Project records are append-only SHA-256 chained under the existing NOX project folder (cs5_project_events.json), not a second DB.
- B01/B02/B05 collect provenance-backed hypotheses, ideas, editorial decisions, brands, forecasts and **unverified** provider receipts.
- B03's actual media generation remains the existing storyboard/ComfyUI/FFmpeg engine. B04's model actions remain the existing P03 ModelCenter.
- Existing original D02/Home/Menu/Work, five approved image identities, 8 CoreIDs, P01 NSIS and P02/P03/P04/P05 source are untouched.

## Ready OSS reuse — do not reinstall or duplicate
| Candidate | Actual owner path / integration | Gate |
|---|---|---|
| Microsoft WebView2 | Original WPF host + CreativeHostBridge.cs | Same-EXE native QA |
| NSIS Modern UI 2 | Installer/NOX-HELION-Setup.nsi, E06 builder | No unsigned/unverified release |
| CommunityToolkit.Mvvm | Optional WPF refactor, NOT installed by this patch | Do not rewrite working host |
| Ollama | Existing P02 OllamaChatClient.cs and Studio engine | Local model installed & user permission |
| restic | Optional existing-owner backup command, not yet bound | Explicit encrypted repo, password and restore drill |
| Playwright | Independent browser checks on original Creative UI | Browser fixture != Windows E07 |
| PSScriptAnalyzer | Optional read-only Windows script QA | Installed runner and scoped scripts |
| GitLab Windows hosted runner | Existing .gitlab-ci.yml tag saas-windows-medium-amd64 | Manual variables / T08/T10 gates; runner availability |

## One verification path (no redundant CI suites)
Run from the repository root:
1. python -m unittest discover -s integrations/creative/tests -p 'test_five_blocks.py' -v
2. node --check integrations/creative/web/five_blocks.js
3. node --check integrations/creative/web/entry.js
4. Existing owner-specific Creative tests, then exact-source SHA readback.
5. Source owner T06 and independent T08/T10 gate; ONLY then authorized GitLab Windows CI and E07 same-EXE QA.

## Proof & limits
- New five-block notes are project-local, with explicit status LOCAL_RECORDS_NOT_E11. **No direct E11/S26 database adapter is falsely claimed.**
- Financial receipt status is REPORTED_UNVERIFIED. It cannot be counted as actual revenue without external provider proof.
- No model weights were downloaded, no backup or cloud action executed, no paid calls, no EXE produced.
- Stop in the existing Studio blocks cs5_append and remains active until the worker lifecycle resets. Reads are allowed.
- E07, 10+10+10 cinema and real cross-process S26/E11 admissions remain HOLD.
- Do not merge until source owner resolves existing PR180 overlap on entry.js and completes same-HEAD review.
