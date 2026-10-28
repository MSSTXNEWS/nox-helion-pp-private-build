# NOX V16 · E06 G2·01 R04 · SOURCE HOLD (coordination only)
RunID: NOX-V16-E06-G2-01-20261028T0913MSK-R04
Owner: E06. Preimage: ABSENT. No UI/host/ZIP/patch deletion; no main merge.
Frozen Git baseline COMMIT SHA-1: 0b3a7d435be735148d64171deb9027093a89646e
Frozen Git baseline TREE SHA-1: f108d604c444f718b32aaecfd07b90b8f91b9a6f
PR66 inventory HEAD SHA-1: bfc318d6e002563995fd05a420c2022b39ef90d9
PR79 prewrite HEAD SHA-1: a7a70ed25f3267ca2ddb4382242b165c7d11bee3
ONLY immutable historical original SourceLock SHA-256: 806c748e939c9acca3c3055ae731a752504ef2723d077c0bb07fd89904fd98df
Historical original Git commit SHA-1: eb46b49fb8a022cefa679afb8606877016808db1 (DIFFERENT provenance)
729 original manifest rows, 67,102,932 uncompressed bytes: MANIFEST VERIFIED, NOT raw ZIP parts or installed application.
Historical ZIP SHA-256: ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a
source_00.part: 20,971,520 bytes / Git blob SHA-1 e484e10d7b4ec9badeaae4c9d3a7e3aee5faa16b / raw SHA-256 N/D
source_01.part: 20,971,520 bytes / Git blob SHA-1 7853cb43ff4ba0ed3023e8d794d8222eedea56a6 / raw SHA-256 N/D
source_02.part: 18,421,306 bytes / Git blob SHA-1 cbd9deb30860737f15e2adbaef2eaaf5d607a0de / raw SHA-256 N/D
Sum: 60,364,346 bytes; cannot promote historical manifest to merged app SourceLock until raw-part bytes/owner receipts.
Approved D02, Persona, asset SHA and seven small .safetensors: matched HISTORICAL manifest records only; installed model weights N/D.
Owners (SOURCE only; INTEGRATED=HOLD; WINDOWS ACCEPTED=NOT_RUN; accepted %=N/D):
E01 V16.26.3 P01(20%) PR90 HEAD 3ce4fed2cfcc6ecaf186f0f8a56cae12b6b793ab
E02 V16.26.4 P02(25%) PR91 HEAD eab35bb38a7693db53d5d639925aecc8b86f0977
E03 V16.26.5 P03(20%) PR92 HEAD 8d2a3ff44adc43c60e2cea0b8fd8bacc20f9213e
E04 V16.26.6 P04(25%) PR89 HEAD df2be9bd4c0840d3383815876e91326a0ae4fa53
E05 V16.26.7 P05(10%) PR75 HEAD 82f77693bf4f380f972a236cb2909642bb4fabbb
E06 V16.26.8 SourceLock PR79 prewrite HEAD a7a70ed25f3267ca2ddb4382242b165c7d11bee3
E07 QA01..QA10 PR46 HEAD 266c3a520f6d1ee908c2dad0d0397d1c16f0a1cc (base eb46..., not accepted).
Confirmed overlapping paths: PR85/90 d02_admission.py; PR78/92 p03_modelcenter_gate.py; PR83/89 train_qlora.py => HOLD, preserve candidates and order merge by receipts.
No E07 same installed BuildID/EXE SHA; weighted readiness 0.20*P01+0.25*P02+0.20*P03+0.25*P04+0.10*P05 = N/D.
Local immutable-manifest regression: 12/12 PASS after correcting test fixture layout; this is source-only evidence.
Practical lesson (exactly one): apply dual-provenance gate to historical original lock and frozen Git baseline and require raw part SHA-256, not Git SHA-1 or historical CI report, before canonical promotion.
NO NEW SOURCELOCK CREATED. RELEASE BLOCKED; no final EXE.
