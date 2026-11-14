# NOX HELION V16 · E06 #6 · G2·05 R02 · OWNER7 HANDOFF

RunID: `NOX-V16-E06-G2-05-20261028T0712MSK-R02`. Source-only candidate on GitHub draft PR #70: https://github.com/MSSTXNEWS/nox-helion-pp-private-build/pull/70 . No main merge or production install. Immutable packaging baseline Git commit SHA-1 `0b3a7d435be735148d64171deb9027093a89646e`, Git tree SHA-1 `f108d604c444f718b32aaecfd07b90b8f91b9a6f`. At the read, `main` matched the baseline. PR #66 is inventory, not complete runtime SourceLock. Latest owner6 R03 original 729-file manifest metadata exists with declared SHA-256 `806c748e939c9acca3c3055ae731a752504ef2723d077c0bb07fd89904fd98df`; raw bytes of all 3 source parts have not independently passed SHA-256 readback in this cycle. **INTEGRATED=HOLD**.

## Single existing runtime, zero duplicate providers
The P03 ModelCenter routes are registered solely through existing owner3 `P03OneHostPort` with owner2-installed Ollama client; cards are discovery, not downloadable weight files. Pull, GGUF import, STOP and Retry remain guarded by the real owner3 backend and native consent. The adapter never downloads or creates an Ollama listener. The P05 owner5 feeds and hardware snapshots are read-only with RunID, data/source UTC and N/D for unverified inputs; the adapter does not fetch news/weather/market itself. Only the existing `NOX-INSTALLER-EVENT-v3` publisher may emit canonical events. P02 RU↔ES/MAESTRO/call handling remains owner2 with actual installed engines and provider quote plus native approval; no automated paid calls. Mobile is native peer/origin/CSRF authenticated only, no public host/gateway port and no claim of responsive UI admission without owner1 acceptance.

## R02 observed defect and precise patch
During readback, `G2OneHostBinder.bind` calculated `mobile_routes` only when the host-attested private gateway was ready, but then unconditionally registered `mobile.connect` whenever the mobile object existed. This contradicted existing test_29 and could leave a misleading offline port in the registry. **FIXED** by binding only when `"mobile.connect" in mobile_routes`; even an existing binding immediately reports HOLD when its real native gateway goes offline. Owner SHA-256 receipts are now copied on binder construction so an outside mutable mapping cannot alter the seal between preimage admission and route registration. No source file outside E06 adapter or E06 test/workflow scope changed.

R02 tests added: test_30 gateway revoked after bind, test_31 mutated external receipt dict must not alter snapshotted receipt and original `BoundPort.evidence_id` source contract, test_32 nonmapping receipts reject. Existing test_29 checks no port registration when private gateway starts offline. Suite now has **32 defined** Windows-targeted tests; verified **Windows execution still NOT_RUN** if latest CI job has zero steps. Do not report definitions as PASS.

## TURBO10 G2-05-01…10 status
01 V16/master/E06/lessons read and immutable baseline compare PASS; 02 source-lock + owner preimage admission SOURCE guard, native lock HOLD; 03 one PACK01 worker/P02 Ollama SQLite STOP owner source reused, native EXE HOLD; 04 P03 original onehost ModelCenter registration SOURCE, real Pull/GGUF/Retry NOT_RUN; 05 P05 events single publisher SOURCE, real host connection HOLD; 06 telemetry/feed UTC and N/D guards SOURCE, real hardware/feed HOLD; 07 P02 RU-ES/MAESTRO/SIP provider quote guarded SOURCE, real voice/SIP NOT_RUN; 08 Mobile origin/CSRF/private peer and offline binding FIXED at SOURCE, actual gateway HOLD; 09 registry rollback and immutable receipt mapping SOURCE, raw extracted SourceLock HOLD; 10 32 Windows-targeted test definitions + E06/master/one lesson+readback; component Windows NOT_RUN until steps execute. Actual installed EXE and E07 acceptance NOT_RUN.

## Seven independent indicators + weighted formula
| Executor / task ledger | SOURCE | COMPONENT VERIFIED | INTEGRATED | WINDOWS ACCEPTED | Completion |
|---|---|---|---|---|---|
| E01 / V16.26.3, G1.01–10 | PR77 and earlier owner1 drafts | isolated tests only | HOLD | NOT_RUN current | N/D |
| E02 / V16.26.4, G1.C14 | PR76 + original P02 | 31 local policy tests, original Windows N/D | HOLD | NOT_RUN | N/D |
| E03 / V16.26.5, G1.03.01–10 | PR78 and PR17 originals | 32 staged local cases, native models N/D | HOLD | NOT_RUN | N/D |
| E04 / V16.26.6, G1.04 | PR74 + GPU/RAG originals | GPU physical N/D | HOLD | NOT_RUN | N/D |
| E05 / V16.26.7, G1.05 | PR75 + events original | 18 local Node policy cases, sensors N/D | HOLD | NOT_RUN | N/D |
| E06 / G2-05-01–10 | PR70 R02 E06-only patch | 32 Windows tests DEFINED, runtime NOT_RUN | HOLD SourceLock/host | NOT_RUN | N/D |
| E07 / QA01–QA10 | PR46 diagnostic source | old installer diagnostic, not current app | HOLD | NOT_RUN final | N/D |

Weighted TOTAL = 0.20*P01 + 0.25*P02 + 0.20*P03 + 0.25*P04 + 0.10*P05 = **N/D**; unsealed denominator and no single same-SHA EXE mean no valid product %. Approval/production release **BLOCKED**.

## Targeted independent #7 steps
1. Owner6 independently SHA-256 checks the raw `source_00.part`, `source_01.part`, `source_02.part`; reconcile R03 729-member list and all owner receipts/preimages on ONE source tree, not PR66 inventory alone.
2. Pin exact PR70 HEAD, all 7 E06 file blobs and SHA-256 receipts. Run `.github/workflows/nox-e06-g2-space-mobile.yml` on actual Windows with 32 executed cases; check rollback and private auth on original owner modules, not mock replacements.
3. Bind exactly one original WPF/WebView2/Python host and events.v3; verify P02 STOP/SQLite, P03 installs consent/provider rights, P05 live date/source, voice real ASR/TTS, SIP provider quote/native acceptance, mobile private TLS/CSRF. Missing provider => HOLD.
4. Create only approved combined installer, compare installed EXE BuildID/SHA-256 with current same-tree source; #7 independent install/update/rollback/uninstall, D02/8 CoreID/WOW, GPU checkpoint and resource use. Do not call this diagnostic source proposal an accepted EXE.

Exactly one practical self-improvement: **admit a route only from the same frozen owner-receipt snapshot and current native availability gate; revocation must immediately fail closed, and add a negative regression before promotion**.
