# NOX HELION EXPRESS INTEGRATOR · FASTLANE-2 · OWNER READY

**Scope:** existing PR #162 Windows x64 loader only; additive developer-tool files, no new runtime, backend, installer, database or scheduler. This is not the main NOX Release 1.

- Target: `coordination/e06/fastlane2_accelerator.py`, `tests/e06/test_fastlane2_accelerator.py`, `coordination/e06/FASTLANE2_HANDOFF.md`.
- Canonical source at creation: PR162 HEAD `319052e84bfa3dccc115b568c8f158a58123d897`; mandatory fresh HEAD/preimage at merge.
- 34 source-level tests executed successfully on Python 3.13; Windows / E06 / E07 not run.
- Origin: earlier FASTLANE-2 source candidate, with 10 new regression checks for ERR-25 / previous NOX process failures.

## Most important fixes after first candidate

1. Input JSON duplicate keys (including nested) and nonfinite large exponents denied; no shadowing TaskID, consent, source head, or lease evidence.
2. Overlapping active TaskID or active file leases fail closed. A 10-minute elapsed time NEVER releases an active owner's claim.
3. Dependency chains of 1,000 tasks checked iteratively; cycles fail closed, not a recursion crash.
4. Immutable off-tree handoff refuses a no-op identical to current Git blob, binary/non-UTF8, stale exact HEAD, in-repo target, symlink/reparse, duplicate output, and changed candidate bytes.
5. Independent free TaskID selected without touching the busy patch. No bypass of A/B owner CAS/readback or actual G1-G4.

## Real integration contract

1. **I0 sole canonical writer**: verify exact current PR162 HEAD, absence of these target paths and no other active I0 CAS; use original immutable Git blobs or patch with expected HEAD; one material commit with source+test+this readme, Git readback.
2. Add this as a **pre-task selection utility in existing worker execution**, not a new scheduled service. Input ledger/leases must come from authenticated current PATCH-A/B owner receipts (not browser/model suggestions). Each worker checks active owner and cross-lane conflicts. If target busy, the tool returns a non-overlapping off-tree TaskID; group-owner later CAS-merges the full inherited A/B diff; I0 ultimately merges a SEALED group. Never claim an off-tree candidate DONE.
3. Command: `python coordination/e06/fastlane2_accelerator.py plan --repo <approved-pr162-checkout> --ledger <real-ledger-json> --leases <real-leases-json> --acceptance <real-gate-evidence> --lane A --task A01`. `handoff` only accepts an immutable approved off-tree candidate, keeps SHA and receipt; it **does not write Drive**. A true Drive `requiredRevisionId` CAS must be handled by the existing authenticated group owner.
4. Run `python -m unittest discover -s tests/e06 -p 'test_fastlane2_accelerator.py' -v` in real PR162 checkout; CI must run the same source test on a working runner. All source staging/SourceLock changes must be pinned and reviewed if later bundled; this helper is developer-only by default.
5. Source states are **NOT** installed Windows evidence. Real E06 Windows runner is still unavailable (GitHub hosted Ubuntu+Windows jobs pre-first-step failed), and actual A1 WPF signed owner callbacks are a separate blocker. Do not mark release or ModelCenter AI running without actual Ollama model.

## G1–G4 and task stages

**G1 REGISTRY** exact current source and rights; **G2 OWNER** group lease/CAS & I0 sole PR; **G3 AI** real installed P02 model/native SID/ACL/STOP; **G4 WINDOWS** native compile, Setup SHA and independent E07 on SAME SHA. For this additive source candidate G1 is source-only, G2 not claimed, G3/G4 not run.

Phase order: **FAST FirstBoot → full installer-loader V16 → main NOX Release 1 → free evolution**. Free exploration may generate candidates, never unchecked production code or downloads. Ownership, security and user confirmation apply at every phase.
