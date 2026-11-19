# Supplemental acceptance rollup design

Date: 2026-11-19

## Decision

Do not add supplemental sidecar records to the frozen 295-task receipt count yet. Keep these values separate:

- **Original receipt count:** derived only from the frozen work_receipts.json acceptance contract.
- **Supplemental accepted count:** a future, separately labeled count of unique original TaskIDs supported by strictly validated append-only evidence.
- **Original acceptance added:** remains zero unless a separate authoritative ledger/catalog revision explicitly changes it.

The repository has no demonstrated in-repo wiring from the runtime 295-task status path to the evidence addenda directory. The only task-progress implementation found is complete_executor_20261118/source_baseline/work_progress.py, which summarizes work_tasks.json, work_ideas.json, and work_receipts.json. The native dispatcher’s project_status() reports subtask/catalog status and original_task_acceptance_added: 0; it has no configured addenda path and is deliberately scoped to SUBTASK_COMPLETED_ORIGINAL_NOT_ACCEPTED. Connecting evidence files to either code path without establishing the deployed caller and source trust boundary could publish a count that no live consumer actually uses or overstate self-asserted sidecar data.

## Schema and trust gaps

The newer GPU addendum (blob 18a07178ab56e3eab9b2d5a88431dd26deef5e1e) has a usable binding shape for Task 2V14-12: the immutable manifest blob and task spec_sha256, criteria.addendum_assessment=ACCEPTED, acceptance_binding.evidence_pointer=#/additional_evidence_records/0, a record with the exact task_id and result=ACCEPTED, and a second evidence pointer into the same document.

The earlier snapshot addendum (blob 2cc60b0d840c33c6a1e46259432273eead878608) represents 2V14-12 as criteria.addendum_assessment=ACCEPTED with acceptance_binding.evidence_pointer=#/evidence/hardware, but has no corresponding accepted additional_evidence_records entry for that task. A consumer must not silently treat both forms as equivalent. Older forms should be excluded until explicitly migrated through a new append-only record.

The JSON fields, workflow URLs, run IDs, owner comment IDs, and the word ACCEPTED are claims in the addendum. The current runtime source has no verifier that checks the workflow run, owner authorization comment, or the reviewed Git commit. Structural validation alone can establish a well-formed, task-bound sidecar record; it cannot independently authenticate the claimed native run or owner approval. A trust policy is needed before calling its total an authoritative acceptance count.

## Required consumer contract

When an active caller and trust policy are established, add a read-only rollup alongside the existing receipt-derived counts. Do not modify all295_execution_disposition.json, work_receipts.json, task rows, or original_acceptance_added.

For each candidate JSON addendum, count a unique TaskID only when all checks pass:

1. The addendum has schema NOX_NATIVE_EVIDENCE_ADDENDUM_V1, append_only=true, and references the exact frozen all295 manifest blob.
2. The TaskID exists exactly once in the frozen manifest; the addendum’s criteria key, scope list, record TaskID, and manifest record key all match.
3. The manifest’s spec_sha256, criteria spec_sha256, and record criterion spec_sha256 are identical.
4. criteria[task_id].addendum_assessment and the pointed additional_evidence_records[index].result both equal ACCEPTED; the criteria binding pointer resolves to that exact record.
5. The record’s own evidence_pointer resolves to a non-empty object in the same addendum; workflow run/job IDs and owner authorization ID match across binding, record, and evidence.
6. The source artifact is a regular non-symlink JSON file, parsed with duplicate-key rejection, and the rollup reports its repository path, URL, file blob/hash, record number, evidence pointer, run ID, and task spec SHA.
7. Duplicate accepted records for one TaskID count once. Invalid or unreadable addenda make the scan incomplete/HOLD; they must not be silently skipped while publishing a complete total.

The result should be exposed under a new field such as supplemental_acceptance, with its own state, accepted_unique_task_count, scan_complete, items[], and original_acceptance_added=0. It must not change the existing tasks.completed, total.completed, or final acceptance result.

## Frozen inputs

- all295_execution_disposition.json: blob f5c45dc8919b1b800e89a421676a3627e75fb3bb
- work_receipts.json: blob 6a9c71393735dbc4b5c1577272f22cef38ab6338
- Dispatcher status test asserts 295 registry entries do not mean 295 accepted tasks: test_owner_catalog_progress.py, blob fea214f4e5ced3252adcce5788d3eb54884bcf71

This note changes no original acceptance state.