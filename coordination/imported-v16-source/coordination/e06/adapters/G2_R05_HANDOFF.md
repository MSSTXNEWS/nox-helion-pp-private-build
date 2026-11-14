# NOX V16 · E06 G2·05 R05 · E07 HANDOFF
RunID: NOX-V16-E06-G2-05-20261028T1009MSK-R05
Immutable baseline: main 0b3a7d435be735148d64171deb9027093a89646e; tree f108d604c444f718b32aaecfd07b90b8f91b9a6f.
Source candidate parent PR96 head c181c4ce33bd208923d6bbc88f7ec5edff9f3165; NEW DRAFT branch e06/v16-g2-05-runtime-no-loss-20261028-r05. PR66 INVENTORY ONLY, raw source_00/01/02 SHA-256 plus 729 extracted members UNVERIFIED => integration HOLD, no merge.

## Technical TaskID ledger (10 scopes; source only, not ten release PASS)
1. G2-05-R05-01: R05-01 frozen main compare; SOURCE CANDIDATE.
2. G2-05-R05-02: R05-02 E06 ownership preimages; SOURCE CANDIDATE.
3. G2-05-R05-03: R05-03 P02 mandatory original six; SOURCE CANDIDATE.
4. G2-05-R05-04: R05-04 P03 mandatory original three; SOURCE CANDIDATE.
5. G2-05-R05-05: R05-05 cross-owner route+receipt collision; SOURCE CANDIDATE.
6. G2-05-R05-06: R05-06 P05 paired VRAM measurement; SOURCE CANDIDATE.
7. G2-05-R05-07: R05-07 P05 integer bytes + provenance; SOURCE CANDIDATE.
8. G2-05-R05-08: R05-08 events.v3 bounded payload and seal-at-publish; SOURCE CANDIDATE.
9. G2-05-R05-09: R05-09 SIP provider recheck + Mobile existing auth; SOURCE CANDIDATE.
10. G2-05-R05-10: R05-10 Windows-targeted 13 regression tests + SHA readback; SOURCE CANDIDATE.

P03: Reuses existing P03OneHostPort and original downloader; stricter receipt checks before accepting claims of registered ModelCenter models.catalog/installed/digest. Pull/GGUF/Stop/Retry remain owner-gated; R05 owner3 queue attestation from PR102 NOT integrated until the native SourceLock/owner receipt is sealed.
P05: Reuses E05 snapshot + single events.v3 publisher; rejects orphan/inconsistent/fractional VRAM, blank feed source, large/non-text event messages, revoked SourceLock between checks. No guessed prices, sensors, progress.
P02: Original Ollama/chat/SQLite untouched. Voice and MAESTRO only existing owner callbacks. SIP calling is not invoked; existing provider health rechecked at runtime, host native consent mandatory.
NOX Mobile: existing private HTTPS gateway/auth/CSRF and host-only routes unchanged, no listening server/public Ollama/new worker.
Tests: 59 in-process definitions in tests/e06/adapters/test_g2_space_mobile.py, 13 new negatives. This run DOES NOT prove Windows execution or installed EXE. GitHub CI prior run failed before steps, status NOT_RUN until a genuine Windows job log and same-source receipt are obtained.

## SHA-256, Git blob SHA1, immutable owner receipts
- coordination/e06/adapters/g2_space_mobile.py; OWNER E06#6; RunID NOX-V16-E06-G2-05-20261028T1009MSK-R05; pre SHA256 5683fe72dcd1afb0115d8974fe5609817bff6ba054fbfd2c76a33209befecf52; post SHA256 07777f916aeb5e4a86553d573d9526abbb7c75499260c225c649507737f3461d; pre Git blob 5766343c2bbbfe9fcf76ad6de50a23b5530fe66e; post Git blob 8f0dacc521612206e8edfad6a41ac85b5e0162dc; commit f25cb19451a64332f914ba26ab7dd45bb5d9e6e5; diff: P02/P03 owner registration receipt+mandatory route admission; P05 VRAM/blank provenance; single events.v3 message/source recheck; SIP provider runtime revocation; GitHub readback PASS
- tests/e06/adapters/test_g2_space_mobile.py; OWNER E06#6; RunID NOX-V16-E06-G2-05-20261028T1009MSK-R05; pre SHA256 1593f3b90db2f7f1efcbeeb9841844883b3e6bbbf8ef2f5412e39b1d5c3f1bac; post SHA256 72cb2cb6756d8706826060da6221a6b9c4818351513e4d2988ae2fae691841b0; pre Git blob 4ad9155256a2a8822045343eebf652c4cfa58e11; post Git blob 4785dd0b2e7d56bc617489e29809b4cd3785f817; commit 71534a13fe005d755a6834d7cc5e68af4682c404; diff: 13 new negative in-process tests 47–59 (now 59 defined, NOT_RUN); GitHub readback PASS
- .github/workflows/nox-e06-g2-space-mobile.yml; OWNER E06#6; RunID NOX-V16-E06-G2-05-20261028T1009MSK-R05; pre SHA256 8de8c3c79871a3237903c6d77db5fb1a3393097115a1d898788d49289bcd929d; post SHA256 f68ed5f2b38f3776d49088abd7e710be4fcc0827124cd5311d29844c497eb87f; pre Git blob 425a9c68462f6f114c5a74b3bcaf661637810676; post Git blob 747ba081d6f331eb5e8120dea8749491415b77d0; commit aebbf5c815ab05f4b202b0b271a61d42b77144fb; diff: R05 branch trigger and honest defined-test count; GitHub readback PASS
Other added report/receipt files: PRE=ABSENT; post SHA-256/Git blob tracked by GitHub readback, not fabricated.

## Seven independent indicators
E01 V16.26.3/P01 PR101 SOURCE partial, component cross-file mismatch HOLD, integrated HOLD, Windows NOT_RUN, N/D.
E02 V16.26.4/P02 PR100 SOURCE, 18/18 offline fixture per owner, integrated HOLD, Windows NOT_RUN, N/D.
E03 V16.26.5/P03 PR102 SOURCE, 90/90 offline fixture per owner, integrated HOLD, Windows NOT_RUN, N/D.
E04 V16.26.6/P04 PR89 SOURCE, GPU REAL NOT_RUN, integrated HOLD, Windows NOT_RUN, N/D.
E05 V16.26.7/P05 PR98 SOURCE, 65 local fixture tests per owner, integrated HOLD, Windows NOT_RUN, N/D.
E06 V16.26.8/G2-05-R05 PR96+new draft SOURCE, 59 DEFINED NOT_RUN, integrated HOLD, Windows NOT_RUN, N/D.
E07 QA01–10 PR46 SOURCE historical, 0/10 current installed EXE checks, integrated HOLD, Windows NOT_RUN, N/D.
Weighted 0.20 P01 + 0.25 P02 + 0.20 P03 + 0.25 P04 + 0.10 P05 = N/D (missing TaskID acceptance receipts).
HOLD: current head/frozen main matches snapshot, but RAW original parts SHA-256 and canonical 729-file SourceLock unsealed, owner reconciliations unresolved, single installed EXE untested. No assets, D02/WOW, original owner sources, ZIP or EXE modified/deleted.
ONE LESSON: A registered route is not a verified working backend: require exact mandatory original route IDs, matching owner receipt on actual host port, and runtime re-attestation of mutable provider/source readiness before native dispatch.
HANDOFF E07 #7: verify 59 tests on Windows against pinned original P02/P03/E05/PACK01, reconcile PR102 P03 attestor, original 729 SHA manifest, run same-BuildID/EXE SHA install/update/rollback; do not mistake 59 definitions for 59 PASS.
