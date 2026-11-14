# NOX V16 · E06 G2·05 TURBO10 R09 → E07 independent QA

RunID: NOX-V16-E06-G2-05-20261028-R09
Global immutable baseline: 0b3a7d435be735148d64171deb9027093a89646e
Git tree (global): f108d604c444f718b32aaecfd07b90b8f91b9a6f
Exact owner E06 R08 parent: 4f9b81b37bb12897edc0434282011cd028087e00
R09 branch: e06/v16-g2-05-gpu-coherence-20261028-r09
Original source_00/01/02 raw 3-part SHA-256 + 729 extracted files: NOT_VERIFIED / HOLD
Source owner scope: coordination/e06/adapters/, tests/e06/adapters/, coordination/e06/adapters/*receipt/*handoff only.

## Concrete R09 changes (source candidate, NOT installed)
- Existing g2_space_mobile.py now reads only preexisting E05 Hardware Snapshot SampleId/sample_id; contradictory aliases, unsafe sample ID and invalid observations become N_D.
- New g2_gpu_sample_gate.py checks a single GPU tile: same provider + <=5s UTC observation window + coherent optional native SampleId for all LIVE metrics. Same physical DeviceId continues to be checked by existing R08 g2_gpu_provenance.py.
- Existing host binder / one worker / one events.v3 unchanged. No second network listener, Ollama public endpoint, sensor source, auto-dial, paid SIP, market quote or model download.
- 12/12 isolated Python helper unittest PASS locally (Linux Python), py_compile PASS. GitHub code readback required. 8 additional host-contract test cases defined; Windows NOT_RUN. Total defined G2 component cases: 125 = R08 105 + R09 20; these are NOT 125 passes.
- Windows workflow update to add R09 branch could not be committed (tool safety block); DO NOT claim a successful R09 Windows job. E07 must exercise pinned same-owner tests in approved Windows CI.
- P03 Ollama pull/GGUF/STOP/retry and P02 voice/MAESTRO/SIP remain existing owner contracts; runtime integration NOT_VERIFIED; private mobile HTTPS gateway/auth NOT_VERIFIED.
- Latest approved frozen main compare IDENTICAL; all new work isolated stacked on R08. No main, D02, WOW, P01–P05, archives, models or EXE modified.

## E07 acceptance required
1. Exact R09 source file SHA-256, Git blob SHA-1 and patch receipt readback.
2. Compare R09 only against immutable R08; owner map collision check.
3. Test P05 owner PR145 sample_id and pinned native C# DeviceId field aliases using actual owner-hash receipts.
4. Run all 125 Windows pinned-owner component scenarios with real recorded steps and artifacts; do NOT accept nonexistent runner steps as PASS.
5. Verify source_00/01/02 parts, all 729 extracted SHA-256, one sealed unified SourceLock and one host.
6. Real P02/P03/P05 integrated route tests, NOX Mobile private authenticated gateway only, no public Ollama.
7. Execute same BuildID/EXE SHA installed Windows acceptance including NSIS install/update/rollback and visual/AI/voice paths.
RELEASE = HOLD until all relevant gates independently pass.

## Seven separate indicators (TaskID ledger references)
E01 V16.26.3/P01 PR144 | SOURCE candidate | synthetic reported | INTEGRATED HOLD | WINDOWS NOT_RUN | N/D
E02 V16.26.4/P02 PR146 | SOURCE candidate | 49 offline mocked reported | INTEGRATED HOLD | WINDOWS NOT_RUN | N/D
E03 V16.26.5/P03 PR142 | SOURCE candidate | 150 offline reported | INTEGRATED HOLD | WINDOWS NOT_RUN | N/D
E04 V16.26.6/P04 PR143 | SOURCE candidate | isolated CPU only | INTEGRATED HOLD | WINDOWS NOT_RUN | N/D
E05 V16.26.7/P05 PR145 | SOURCE candidate | offline owner Node only | INTEGRATED HOLD | WINDOWS NOT_RUN | N/D
E06 V16.26.8/G2-05-R09-01..10 | SOURCE candidate | 12/12 isolated helper PASS, host 8 DEFINED/NOT_RUN | INTEGRATED HOLD | WINDOWS NOT_RUN | N/D
E07 QA01..QA10 PR46 | historical source evidence | final installed Windows EXE 0/10 | INTEGRATED HOLD | WINDOWS NOT_RUN | N/D
Weighted = .20*P01+.25*P02+.20*P03+.25*P04+.10*P05 = N/D (missing accepted receipts). No artificial percentages.

## Exactly one applied lesson
GPU_COHERENT_NATIVE_SAMPLE_GATE: never combine multiple GPU LIVE readings into one tile unless physical DeviceId (R08), provider, 5s observation window and optional native SampleId all agree; otherwise N_D. Retain CPU independently.

Owner: E06 (#6). E07 is independent, never a self-acceptance.
