# NOX V16 · EXPRESS CRITICAL PATH · MANUAL #2 independent QA execution gate
RunID: NOX-V16-MANUAL02-R26-EXPRESS-20261030-R02
Source: PR #162, observed HEAD `d9dfa486eae186ed0efac32bccecb7d6bac769f9` (DRAFT; not frozen).
Status: SOURCE_READY HOLD / GitLab CI NOT_AUTHORIZED / E07 NOT_RUN / RELEASE HOLD.

## Scope & precedence
Existing NOX V16 §33 56 functional rules, §§54–56/R29, R24–R26, R25 manual-first. Existing manual #1 sole PR162 product writer; manual #3 P04/P05 owner donor; manual #2 independent read-only product QA; T02 sole Master/E06/Lessons/ERROR_REGISTER writer. This file is **QA handoff on isolated manual2 branch only**. It is not acceptance, owner authorization, release instruction, new TaskID, or a change to source. All historical DONE, original 3 archive parts/729 members, D02/WOW200, CoreID8, Persona5, PACK01/02, STOP/ACL/consent/NO-LOSS retained.

## Fastest owner-to-QA handoff order, no synthetic tasks
1. P0 P03 existing `P03_QUEUE_GGUF_STOP_RETRY`: manual #1/T06 integrate **only** R16 optional ACK jobId/modelTag validation from already-prepared donor `8ac474da750d540e68a16566b69be276e247d358` using fresh exact PRE in `Packages/P03/Source/P03.ModelCenter.Wow/ui.js`. Do not overwrite integrated R15 consent 13-field invalidation or reviewedTag safety. Reuse exact existing source test `tests/P03/test_G2C_G3B_R16_queue_ack_binding.cjs` and `tests/P03/test_g2c_g3b_consent_snapshot_r24.cjs`. Owner CAS + readback -> manual #2 independent repeat on new SHA.
2. P0/P1 P01: guard Windows unsafe path components in `coordination/e06/t06_owner_receipt_same_head_gate_r23.py` and reject duplicate object keys before `ConvertFrom-Json` in BOTH `stage/proposals/P01/C09/Installer/Verify-Payload.ps1` and `Remove-InstalledPayload.ps1`. Fail closed before activation/deletion. Reuse existing owner candidate, PowerShell 5.1 negative fixture and verified readback, not a second installer.
3. P0 P04/P05: manual #3 owner source+test+receipts from PR #221, checked exact PRE by manual #1/T06. Preserve RAG/GPU rights/STOP/thermal checks and SPACE freshness/mobile consent/epoch. Do not regress the already integrated `Packages/P04/model_snapshot_probe.py`: PR221 new Windows path hardening is donor until T06 integration. No source acceptance by mere donor presence.
4. P0 P02/Host50: prove genuine WebView2->onehost->Python/SQLite/Ollama/voice binding, 50 route owners and native permission receipts. Keep historical Host50 source HOLD 13, unbound 11, native pending 14 as separate ledgers. No invented route PASS.
5. Manual #1 T06: owner acceptance 8/8 + original ZIP/729 raw identity + current tree/manifest/owner receipts/NO-LOSS, only then deliver frozen-candidate SHA. Manual #2/T08 independently verify on that exact SHA and all changed risk boundaries. T09 freeze -> T10 SOURCE_READY; T11 GitLab Free GET-only readiness can run alongside source work but no EXE/NSIS/CI build. Separate explicit approval for T12 Windows build, T13 actual same-BuildID E07 10/10, T14 genuine P0/P1 fixes, T15 release.

## Targeted independent QA already executed on product HEAD `d9dfa486eae186ed0efac32bccecb7d6bac769f9`
- P03 R15 consent invalidation: existing committed test source Git blob `0ec5792321a42a259698aa6aaf53bf9c88ed903c`, actual UI Git blob `1eaf4435a6ae788b29340e67e9d52bb9fedf1bcf`. Executed the existing source-equivalent 12/12 fixture in V8 with mocked DOM/host and minimal HTTPS URL test adapter; PASS SOURCE ONLY, NOT native.
- P03 R16 queue target binding: exact existing donor test blob `3651a606ca168c19ea7351f38bab0c3d06fd619e` executed in V8 with fake local fs/path/assert against actual canonical UI Git blob `1eaf4435a6ae788b29340e67e9d52bb9fedf1bcf`. FAIL after 4th assertion: `other job ACK must not unlock STOP`. Same exact test on donor UI Git blob `d6c790f755d462bf1a266262d8dd1af1da723cff`: PASS 13/13. Donor not integrated; no Windows host QA.
- P01 payload manifest: independent source read of the two current PowerShell scripts reveals raw `ConvertFrom-Json` without explicit strict JSON duplicate-member rejection; P1 ambiguity, existing `ERR-SRC-004`. Native PowerShell fixture NOT_RUN.
- P04 PR221 owner branch latest observed `d62117b218f8cf435d267d5b518470f1a18595a1`; its `model_snapshot_probe.py` candidate blob `c0286fe58c020835ec1fd8c4a7b6d1345f115598` is NOT in canonical HEAD (`f5cf5df231ee9ba4344a6445358034b5aaad9241`); owner runtime tests NOT_RUN.

## Policy to maximize speed without cutting quality
- READY-first; no duplicate donor rewrites or new UI/backend; one T06 integration writer, short owner receipt and targeted tests per compatible batch.
- Manual #2 independently reruns only changed files + dependent security/STOP/ACL/consent/rollback/no-loss invariants; one final whole-tree source gate before freeze. Never carry QA_ACCEPTED or BINARY_PASS from old HEAD.
- T02 alone CAS-appends to common Git register/Master/E06/Lessons. GitHub issue #177 handoff is not journal PASS. Control center data remains SNAPSHOT_NOT_LIVE until T02 confirmed readback.
- Source-only tests never count as installed Windows E07; E07 stays 0/10 until one authorized BuildID/EXE SHA and actual E2E.
- All P01–P05 accepted percentages N/D without frozen TaskID denominators; source presence, integration, independent acceptance, build and release are separate states.

## Next checkpoint
Manual #1: P03 R16 integrated exact SHA + both negative tests, P01 source integrity. Manual #3: P04/P05 donor readback. Manual #2: immediate independent same-HEAD diff QA. T02: index existing `ERR-SRC-004`, `ERR-SYS-002` once and acknowledge CAS. Do not freeze or compile while missing mandatory functions.
