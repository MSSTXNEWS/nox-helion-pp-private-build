# NOX V16 · R22 VERIFIED EXECUTION DELTA · 2026-10-29

**Scope**: Windows EXPRESS INTEGRATOR source-only. This does not change owner permission, 56 canon rules, original 729 source files/3 ZIP parts, D02/WOW200, 8 CoreID, 5 Persona, P01-P05 weights 20/25/20/25/10, STOP/ACL/native consent/NO-LOSS, PACK01/02 or prior DONE. Three manual roles unchanged: #1/T06 sole PR162 source writer; #3 isolated P04/P05 developer; #2 independent QA. T02 sole shared ERROR/Master/E06/Lessons writer. T12-T15/build/EXE/NSIS/GitLab CI/E07 remain paused until authorized SOURCE_READY.

## Previously missed defects and repairs
1. **Deployed R21 Git test imported obsolete functions** reconcile/preview; actual R21 exposes queue_preview. The deployed Git test was replaced and checked by exact blob readback.
2. **R21 stale HEAD had no regeneration**. R22 flow_r22.py accepts the saved R20 schema, current authenticated HEAD as a string, full current JSON register *bytes* and the CURRENT Git blob SHA. It verifies byte-identity using Git blob SHA-1, duplicate JSON keys, all historical error IDs, status counts, owners and dependency DAG, then regenerates an explicit READ_ONLY_NOT_AUTHORIZED proposal. No merged commits, no remote locks, no QA or release authorization.
3. **Git-layout module import**: R22 resolves the sibling r21/flow_r21.py module in the actual coordination checkout, with an offline import-layout test.
4. **QA receipt contradictory SHA bug**: PR162 coordination/automation/t08/t08_autofix_closeout_gate.py currently uses ANY matching alias in a Git receipt. This allows internally conflicting head/source_head fields to pass the downstream gate. An isolated proposal is at coordination/r22/QA/t08_autofix_closeout_gate_PROPOSED.py plus test_t08_head_alias_conflict_r22.py. Owner/T06 approval/CAS and independent current-head tests REQUIRED. No direct PR162 edit here.
5. **Host50 stage confusion**: frozen legacy source ledger: 37 candidate +13 source HOLD, current owner-binding map: 11 unbound and 14 native_pending. All different denominators. See R22_HOST50_METRIC_SEPARATION.json. Never fake a numeric correction.
6. **T06 repeated failed runs**: platform FAILED may follow real work; inspect PRE/POST HEAD+RunID and verified readback before replay, do not duplicate commit or source patch. Check and fix the root cause of failed Git tree writes; do not remove owner CAS or native security.
7. **Manual QA evidence**: no QA_ACCEPTED for the T08 candidate merely because tests exist in Git. Verify source candidate on exact observed head, targeted regressions and necessary STOP/ACL/consent/NO-LOSS checks; T02 only closes verified incident statuses.

## How to use the new read-only dispatcher
Materialize the two inputs **from their own correct Git refs** (not from stale local clones): coordination/r19/R19_ACTIVE_ERROR_AND_GATE_QUEUE.json from coordination branch, and the entire coordination/ops/NOX_V16_ACTIVE_ERROR_REGISTER.json from the active error-register branch. Obtain the current PR162 HEAD and the actual Git blob SHA for the register using authenticated GitHub. Run from repo root:

python coordination/r22/flow_r22.py path/to/R20_queue.json path/to/current_error_register.json --head CURRENT_PR162_HEAD --registry-blob CURRENT_ERROR_REGISTER_GIT_BLOB --now 2026-10-29T22:00:00+03:00

The output is an offline proposed snapshot + preview. Stale snapshot is refreshed with no false ACCEPTED gate carry-forward; leases are not reassigned. If the tools cannot be run, report TOOL_NOT_RUN. Do not pass user passwords/tokens into receipts.

## Acceptance
Validated offline: local R18+R20+R21 suite 63/63 and R21+R22 suite 32/32 (95 suite tests across two runs, 16 R21 tests appear in both runs and so this is NOT 95 unique tests). Proposed QA gate regression is saved in Git but not yet independently executed on the exact PR162 tree.
