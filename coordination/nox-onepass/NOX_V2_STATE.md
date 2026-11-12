# NOX HELION — V25.1 ONEPASS V2 · factual acceptance (12 Nov 2026)

**Repository scope:** code/testing only; original 10-page site is version-pinned to `b55e9979765ea35449a99f7dc54917cfedcd65bb` in PR #241. This patch is [PR #252](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/pull/252), layered on PR #241, not merged into production.

## Verified
- 292/292 original WEB source files, original D02 and 14 physical-world SHA256 intact in conversation bundle.
- Local `NOX_PREFLIGHT_ONLY=1`: SOURCE PASS, STATIC PASS, 0 missing static references.
- Negative tests: 5/5 PASS from local Node.js 22; source-only GitHub Action PASS on initial PR #252 revision. Results are code contract checks, NOT physical GPU or real native API evidence.
- Previous V25.1 [Chromium run #43146688351](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43146688351): seven browser sizes, ten pages, five V19 scenarios, original V7 audit on same verified checkout.
- Runner changes: recheck seven saved Chromium screenshot hashes and 10 routes; reject missing cached PASS; require recent Windows hardware renderer and seven 7 screenshot hashes; require isolated STOP/S03 and voice RU/ES, trained student weight and Windows sync receipts.

## HOLD / not physically verified
- Actual local OneHost at `http://127.0.0.1:18775/` is not reachable from this agent environment; six read-only checks fail connection. No successful native chat or S03 persistence evidence.
- Actual Windows Edge/GPU hardware test and seven owner-GPU screenshots not run.
- STOP in exclusive test OneHost, persisted S03 across owner-authorized restart, GPU SAFE/telemetry, full-weight student checkpoint/optimizer provenance, Windows sync, quality improvement and final owner visual approval not verified.
- No claim of `FULL_ACCEPTED`, no production promotion, no scheduling or RunPod/Windows restart, no destructive cleanup.

A one-click Windows command exists in the artifact handoff (full ONEPASS bundle), but cannot run on a different machine without the user/host connecting that machine. Never convert static/CI PASS to runtime PASS.
