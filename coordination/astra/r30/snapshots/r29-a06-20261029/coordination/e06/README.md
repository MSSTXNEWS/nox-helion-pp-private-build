# NOX V16 E06 · TURBO10 · NO-LOSS integration preflight

RunID: NOX-V16-E06-TURBO10-20261028-R01
Owner: 6
Base commit (Git SHA-1): eb46b49fb8a022cefa679afb8606877016808db1
Base tree (Git SHA-1): bedea674b77d14d94028ba86251d8f4d690353c1
Immutable original source: source_00.part / source_01.part / source_02.part, untouched.

## Executable gates
1. Pin current Git main commit and native tree.
2. Verify all 3 original archive parts against native Git blob SHA-1 and full reconstructed SHA-256 (requires actual bytes).
3. Freeze 15 live PR candidate heads and bases, preserving existing/old branches.
4. Enforce one approved executor for each exact path.
5. Detect all overlapping changed paths, notably PR #6/#7/#12 for P04.
6. Reject missing, stale or non-typed per-file owner receipts.
7. Quarantine two confirmed historical R11 hash mismatches; retain Drive donor provenance.
8. Reject duplicate events.v3 host/bridge assumptions before actual SourceLock and bridge tests.
9. Preserve seven honest evidence lanes, never infer product progress from CI.
10. Reject EXE release until current source, 1–5 acceptance and E07 same BuildID/SHA Windows QA pass.

## Usage
Python 3.10+ standard library, no new runtime dependency.
python -m unittest discover -s tests/e06 -p 'test_*.py' -v
python coordination/e06/verify_integration.py --manifest coordination/e06/intake.json --source-root PATH_TO_REPOSITORY --out e06-gate.json
Exit code 2 intentionally means HOLD/RELEASE BLOCKED; gate PASS of metadata is not a successful Windows app integration. CI runs deterministic tests, stores machine-readable evidence and must never re-label source candidates as accepted release.

## Absolute function preservation
Do NOT remove D02 black liquid sun, HOME/MENU/CORE, eight CoreID, five Personas, 10+10+10 motion, original NSIS/update/rollback, Ollama, SQLite, voice RU↔ES, MAESTRO, SIP/calls, 24+ model inventory and weights, GGUF import/Pull/STOP, RAG, GPU LoRA/QLoRA, telemetry, NOX SPACE, private mobile gateway, Ctrl+K, approved WOW effects, historical donor archives, licenses or tests. Do NOT merge owner P04 conflicts until owner #4 signs new SHA-bound receipts. Do NOT rewrite historical corrupted master journal.

## Current material blockers
Original archived app source must still be byte-read and inspected. SourceLock of the full *unpacked* app is unavailable. PR12 currently needs a typed receipt refresh and targeted compiler repairs. PR9 isolated CI and PR17 isolated CI are not live host acceptance. Integrated Windows BuildID, physical GPU training, user rights and E07 independent same-SHA verification are unavailable. No final EXE may be issued from this branch.

This branch modifies only integration safety metadata/tests, not original app source or donor packages.
