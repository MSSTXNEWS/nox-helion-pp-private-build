# NOX V16 · E07 BLOCK-01/02/04 · immutable handoff contract

This is a release control artifact, not a substitute for actual installed EXE acceptance.

## Build flow owned by manual #1

1. Freeze ONE PR162 commit SHA and source archive. Run the **existing**
   `coordination/source-lock/verify_original_archive.py` against all three original
   `source_0*.part` files and create a single immutable 729-file source manifest.
   Do not accept an inventory of Git blob pointers as the 729 byte digests.
2. Rebuild the original Python binary from pinned sources. Run one WPF/WebView2
   + P01-P05 + D02/Creative/NSIS pipeline with the existing E06 builder. The
   builder must retain original HOME, exactly 8 CoreID, five Persona, WOW 1–200,
   data stores and every functioning route.
3. Emit `E07_BUILT_HANDOFF.json` using `Emit-E07ImmutableHandoff.ps1` in
   `BUILT` phase. It rejects mismatch of existing 729 receipt, source checkout
   SHA, E06 receipt, physical Setup EXE and WPF EXE SHA. The BuildID is
   deterministic from original source SHA256 + Git commit + Setup SHA + EXE SHA.
4. On clean, disposable Windows VM, install THAT exact Setup and capture actual
   logs for install, launch (PID/window/WebView2), update, rollback and uninstall.
   Preserve immutable installed EXE SHA **before** uninstallation; restore/install
   the same exact binary for the final INSTALLED readback. Use the original
   owner P01 NSIS test workflow where appropriate, not a duplicate installer.
5. Emit `E07_INSTALLED_HANDOFF.json` in `INSTALLED` phase, with actual installed
   exe path and five nonempty log paths. Empty/missing logs or differing installed
   EXE SHA are hard failures. Log presence alone is not proof that tests passed.

## Independent E07 manual #3

Only after receiving exact SourceLock, BuildID, Setup/installed EXE SHA, verified
Windows run and logs, test QA01–QA10 **on the same installed EXE**:

1. QA01 Original 729 source SHA, one BuildID, Setup and installed EXE identity.
2. QA02 Clean install, window/process startup and WebView2 navigation.
3. QA03 Original D02/HELION+eight CoreID/five Persona and full WOW assets.
4. QA04 Real routes/buttons, keyboard, mobile-sized WebView2 responsiveness.
5. QA05 Update/rollback/uninstall and no-loss of user SQLite / files.
6. QA06 Real local Ollama chat/stream/STOP/SQLite/RAG citations.
7. QA07 ModelCenter real Pull/GGUF/Retry with model hash checks.
8. QA08 Real GPU/LoRA/QLoRA checkpoints, pause/resume, hardware limits.
9. QA09 Voice RU–ES, NOX SPACE and live events.v3 correctness.
10. QA10 Security, offline/error recovery, consent and access boundaries.

Each test requires its own fresh Windows evidence, not a source-only fixture or
owner-reported CI green. Acceptance requires independent #3 signed QA and
single frozen SHA throughout. Do not set release_accepted=true here.

## GitHub Actions execution blocker

Recent GH Actions runs failed within seconds before the first job step:
40696135712 (E06 source stage), 40696135687 (729 archive audit),
40696135718 (D02 source gate). Steps were null; downstream ONEHOST skipped.
On these observations the failure is at the Actions execution layer,
**not an observed product-test failure**. The root cause is unknown.
Manual #1 must inspect repository/org Actions policies, billing/minute quotas,
runner availability/permissions and GitHub run/check-suite diagnostics, and
capture actual first-step logs; if cloud runners remain unavailable, use an
authorized clean Windows runner manually, preserving command and artifact hashes.
Never turn an unexecuted job green or disable source/SHA/E07 gates.

## Immutable status at authoring

Source hardening PR186 targets E07-SOURCE-03. This handoff wiring only prepares
the mechanism. Actual final BuildID/Setup SHA/installed EXE SHA are unavailable
until a complete real Windows run. RELEASE HOLD stays until E07 independently
accepts the installed binary.
