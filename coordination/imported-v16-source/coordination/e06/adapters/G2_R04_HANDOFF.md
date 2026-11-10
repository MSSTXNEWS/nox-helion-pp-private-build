# NOX V16 · E06 #6 · TURBO10 G2·05 R04 · E07 SOURCE handoff

RunID: `NOX-V16-E06-G2-05-20261028T0906MSK-R04`.
Owner: E06 #6. Immutable approved **Git** baseline commit `0b3a7d435be735148d64171deb9027093a89646e` / tree `f108d604c444f718b32aaecfd07b90b8f91b9a6f` (confirmed against `main` on this run). Parent candidate PR70 R03 commit `e8aaa8b5e02ee2059357d0f23b1e7aab0e756f3e`; R04 branch `e06/v16-g2-05-provenance-20261028-r04` is stacked and remains DRAFT, **NOT MERGED**. PR66 inventory is not a verified SHA-256 of all three original source parts or the extracted 729 files; SourceLock remains **HOLD**. None of the D02, WOW 1–200, HELION/8 CoreID, five Personas, original owner workers, model weights, archives, SQLite, main or EXE were modified.

## TURBO10 exact TaskID ledger (evidence ≠ final integration)
1. G2-05-R04-01 SOURCE: read canonical V16 (including §36 owner override), master/E06/lessons and latest owner receipts.
2. G2-05-R04-02 SOURCE: verified main commit/tree and PR66 inventory-vs-whole-extracted-SourceLock distinction; raw three-part original/729 SHA-256 HOLD.
3. G2-05-R04-03 SOURCE: compared P03 owner PR92 trusted native queue verifier and existing P03 Ollama pull/GGUF/STOP/Retry; **native queue verification callback not supplied**, actual operations NOT_RUN.
4. G2-05-R04-04 SOURCE: reused original P02 PACK01 host boundary, SQLite/STOP policy; no duplicate LLM/DB; actual voice/ASR/TTS/MAESTRO NOT_RUN.
5. G2-05-R04-05 SOURCE CODE PATCH: P05 weather/news/ECB/BTC/Brent feed timestamps now require `SourceUtc <= FetchedUtc <= SnapshotUtc`; inconsistent provenance yields N_D without synthetic prices.
6. G2-05-R04-06 SOURCE CODE PATCH: E05 CPU/GPU/VRAM sample time cannot postdate snapshot; GPU VRAM used/total must have same native source and observed instant; no sensor generation.
7. G2-05-R04-07 SOURCE CODE PATCH: only existing events.v3 publisher; an `evidence_verified=true` envelope is rejected without an E06-native trusted evidence verifier and repeat owner SourceLock check; no second event bus.
8. G2-05-R04-08 SOURCE CODE PATCH: NOX Mobile second native private HTTPS/CSRF/origin/session attestation rejects consent epoch rotation while host advertises. Existing gateway provider still unproven; zero public Ollama/ports, zero automatic SIP calls.
9. G2-05-R04-09 SOURCE TESTS: nine new negative/positive in-process cases (#38–46) added; 46 total definitions. Windows Actions run 40642362381 FAILURE before any job step (`steps=null`), thus 46/46 **NOT_RUN**, not PASS. Real hardware and installed EXE NOT_RUN.
10. G2-05-R04-10 RECEIPT/REPORT: exact R04 pre/post SHA-256 and separate Git blob SHA-1 attached below and `G2_R04_RECEIPT.json`; E06/master/one lessons append and Drive readback tracked separately; E07 handoff only SOURCE, no release acceptance.

## SHA provenance · E06 exclusively owned files
| Path | Pre SHA-256 | Post SHA-256 | Pre Git blob SHA-1 | Post Git blob SHA-1 |
| --- | --- | --- | --- | --- |
| `coordination/e06/adapters/g2_space_mobile.py` | `c87014721f2abc6f54d0540cef368732e6e83df1fa2baf6f35f500fc657a2b32` | `5683fe72dcd1afb0115d8974fe5609817bff6ba054fbfd2c76a33209befecf52` | `7061401f6b3f8432f82927d2d9c82903c1366c78` | `5766343c2bbbfe9fcf76ad6de50a23b5530fe66e` |
| `tests/e06/adapters/test_g2_space_mobile.py` | `f961d9e40d2c6e11fe2f5b5985992a5fd9df225ce624d2b9febce37ab63022a7` | `1593f3b90db2f7f1efcbeeb9841844883b3e6bbbf8ef2f5412e39b1d5c3f1bac` | `1fe49cbb917d0470f47ebe0d87ee5e1fad598879` | `4ad9155256a2a8822045343eebf652c4cfa58e11` |
| `.github/workflows/nox-e06-g2-space-mobile.yml` | `bd137d4fd2f50588d8c73c62474e13e1c32885cf6bad71b220a8bbd48f13cf06` | `8de8c3c79871a3237903c6d77db5fb1a3393097115a1d898788d49289bcd929d` | `a2039677fc005f19ff342ffba061c66dc3441f6d` | `425a9c68462f6f114c5a74b3bcaf661637810676` |
| `coordination/e06/adapters/G2_R04_HANDOFF.md` | ABSENT | See R04 receipt/readback | ABSENT | See GitHub readback |
| `coordination/e06/adapters/G2_R04_RECEIPT.json` | ABSENT | External readback SHA only | ABSENT | External readback Git blob only |

Exact diff: stacked R04 draft PR Files changed, compare parent R03 `e8aaa8b5e02ee2059357d0f23b1e7aab0e756f3e`. Workflow includes R04 branch but Windows job **failed before any step**; do not confuse authored tests with executed tests. One existing host, one existing event bus, one downloader/worker, one SQLite, no public mobile URL, no actual SIP dial.

## Seven distinct progress indicators (product completion N/D)
| Executor · TaskID · weight | SOURCE | COMPONENT VERIFIED | INTEGRATED | WINDOWS ACCEPTED | Actual task % |
| --- | --- | --- | --- | --- | --- |
| E01 · V16.26.3 · P01 20% | PR85 candidate | owner local partial (not rerun here) | HOLD | NOT_RUN | N/D |
| E02 · V16.26.4 · P02 25% | PR84+PR91 source candidates | local mocked policy tests reported, not native E2E | HOLD | NOT_RUN | N/D |
| E03 · V16.26.5 · P03 20% | PR78+PR92 source candidates | 76/76 owner local policy PASS reported, native queue not verified | HOLD | NOT_RUN | N/D |
| E04 · V16.26.6 · P04 25% | PR83+PR89 candidates | local tests only; real GPU LoRA NOT_RUN | HOLD | NOT_RUN | N/D |
| E05 · V16.26.7 · P05 10% | PR75 candidate | owner Node 53/53 fixture PASS reported; real feeds/sensors NOT_RUN | HOLD | NOT_RUN | N/D |
| E06 · V16.26.8 · G2-05-R04-01…10 | R04 SOURCE, 5 paths scoped | 46 tests authored; Windows NOT_RUN | HOLD | NOT_RUN | N/D |
| E07 · QA01…10 | PR46 historical diagnostics | current same-BuildID/EXE-SHA final Windows QA NOT_RUN | HOLD | NOT_RUN | N/D |

Weighted released product readiness `0.20*P01 + 0.25*P02 + 0.20*P03 + 0.25*P04 + 0.10*P05 = N/D`. E06 source seal and E07 final acceptance are independent release gates; **RELEASE HOLD**.

## ONE practical self-improvement
**Cross-frame evidence causality before exposure.** Treat individually plausible timestamps/flags as insufficient: the native producer's source/fetch/snapshot and sensor sample epochs must be ordered, and an events.v3 `evidence_verified` flag must be backed by existing native receipt verifier before publication. Fail closed / N_D instead of displaying a plausible-looking live fact. This is an E06 integration-adapter safeguard, not new weights/training or a claim of installed proof.

## E07 action / release blockers
1. Obtain the owner6-approved original three archive-part SHA-256, all 729 extracted members/immutable manifest and owner receipts. Check latest E03 PR92 native queue receipt callback and E02 PR91 STOP lease in **one real host**, no incompatible PR merge.
2. Run 46 exact pinned Windows component cases and inspect *non-null job steps*. Reproduce the provenance/CSRF negatives with genuine P02/P03/P05 owners. Reconcile only original host paths under exclusive E06 SourceLock.
3. Validate real Ollama/GGUF/STOP, live sensors/provider timestamps, provider-confirmed SIP with explicit local quote+consent, genuine private authenticated mobile HTTPS gateway and real RU↔ES mic/ASR/TTS. Unavailable => HOLD.
4. Only after owner gates, build one NSIS-installed WPF/WebView2 EXE, test install/update/rollback/NO-LOSS and hand exact BuildID + EXE SHA-256 for **independent E07** acceptance. Do not move main or delete any old branch.

Readback for master/E06/lessons: separately verify after append; if unconfirmed record NOT_SAVED.
