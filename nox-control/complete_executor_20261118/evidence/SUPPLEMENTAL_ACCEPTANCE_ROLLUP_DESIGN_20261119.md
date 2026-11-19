# Supplemental acceptance rollup: contract and status

Date: 2026-11-19

## Implementation status

The NOX progress command now reads supported append-only sidecars and reports a separate supplemental acceptance count, accepted task IDs, source paths/URLs, evidence pointers, task spec SHAs, and run bindings. It keeps that count separate from the frozen 295-task registry and the existing receipt-derived completion count. It never writes the sidecars, all295 manifest, or work receipts.

This helper runs only when the NOX progress command calls summarize(). The repository does not wire it into the live UI or native dispatcher.

## Decision

Keep these values separate:

- **Original receipt count:** derived only from the frozen work_receipts.json acceptance contract.
- **Supplemental accepted count:** a separate count of unique frozen TaskIDs supported by strictly validated append-only evidence and not already accepted in the current receipt count. Existing receipt-backed tasks may show a separately labeled evidence refresh without being counted twice.
- **Original acceptance added:** remains zero unless a separate authoritative ledger/catalog revision explicitly changes it.

The repository has no demonstrated in-repo wiring from the runtime 295-task status path to the evidence addenda directory. The only task-progress implementation found is complete_executor_20261118/source_baseline/work_progress.py, which summarizes work_tasks.json, work_ideas.json, and work_receipts.json. The native dispatcher’s project_status() reports subtask/catalog status and original_task_acceptance_added: 0; it has no configured addenda path and is deliberately scoped to SUBTASK_COMPLETED_ORIGINAL_NOT_ACCEPTED. Connecting evidence files to either code path without establishing the deployed caller and source trust boundary could publish a count that no live consumer actually uses or overstate self-asserted sidecar data.

## Schema and trust gaps

The newer GPU addendum (blob 18a07178ab56e3eab9b2d5a88431dd26deef5e1e) has a usable binding shape for Task 2V14-12: the immutable manifest blob and task spec_sha256, criteria.addendum_assessment=ACCEPTED, acceptance_binding.evidence_pointer=#/additional_evidence_records/0, a record with the exact task_id and result=ACCEPTED, and a second evidence pointer into the same document.

The earlier snapshot addendum (blob 2cc60b0d840c33c6a1e46259432273eead878608) represents 2V14-12 as criteria.addendum_assessment=ACCEPTED with acceptance_binding.evidence_pointer=#/evidence/hardware, but has no corresponding accepted additional_evidence_records entry for that task. A consumer must not silently treat both forms as equivalent. Older forms should be excluded until explicitly migrated through a new append-only record.

The JSON fields, workflow URLs, run IDs, owner comment IDs, and the word ACCEPTED are claims in the addendum. The current runtime source has no verifier that checks the workflow run, owner authorization comment, or the reviewed Git commit. Structural validation alone can establish a well-formed, task-bound sidecar record; it cannot independently authenticate the claimed native run or owner approval. A trust policy is needed before calling its total an authoritative acceptance count.

## Required consumer contract

The read-only rollup is implemented in `work_progress.py` and runs only through the NOX progress command's `summarize()`. It is not wired to the live UI or native dispatcher. It reports the immutable 295 baseline, receipt-derived count, and supplemental evidence count in separate fields. It does not alter `tasks.completed`, `total.completed`, the original final-acceptance result, `all295_execution_disposition.json`, or `work_receipts.json`. Every rollup result exposes `original_acceptance_added: 0`.

Two evidence classes are supported across three exact sidecar forms:

1. **Native run addenda** (`NOX_NATIVE_EVIDENCE_ADDENDUM_V1`). Each sidecar binds a TaskID and exact frozen spec SHA, the pinned all295/work_tasks/work_receipts blobs, and a criteria acceptance pointer to an exact `additional_evidence_records` entry. That record and its evidence pointer must agree on TaskID, ACCEPTED result, scope, workflow run/job IDs, owner authorization ID, and task-specific evidence checks. The #517 GPU inventory and #523 process census variants use distinct record layouts, each validated against its own pins and narrow point-in-time criterion. A native workflow can contain a broader failure/HOLD while a specifically bounded accepted criterion is counted; the output preserves that limitation.

2. **Source criterion addendum** (`NOX_SOURCE_EVIDENCE_ADDENDUM_V1`). Task `4A01` is bound to its exact frozen all295 spec/title and frozen input blobs, plus pinned training-source, tokenizer-asset, and GGUF-route manifests. The tokenizer bytes are opened without following symlinks, bounded to the declared size, read twice, and checked against both SHA-256 and Git blob SHA-1. This source evidence does not imply training admission, downloaded weights, live runtime, or optimizer activity. The sidecar's `original_295_acceptance_increment: 1` remains a sidecar claim; rollup-level `original_acceptance_added` stays zero.

3. **Post-merge source receipt** (`NOX_SOURCE_POST_MERGE_ACCEPTANCE_RECEIPT_V1`). I-49 is present in the frozen all295 manifest with its source routed through the exact pinned `work_ideas.json` blob. The rollup binds the frozen task spec, ideas row, #490 post-merge receipt, corrected comparison artifact, comparator revision, checkpoint-pair fingerprint, and 500-name fingerprint. If the current `work_receipts.json` already contains a valid verified I-49 source receipt, #490 is surfaced as an evidence refresh with supplemental increment zero; otherwise it can add I-49 once to the supplemental accepted IDs. Either way, the frozen 295 total and `original_acceptance_added` remain unchanged.

For each candidate sidecar, the scanner requires a regular non-symlink JSON file with duplicate-key and nonfinite rejection, exact source path/hash reporting, and strict task/spec/source pointer checks. Duplicate accepted TaskIDs count once. Invalid files are listed with exclusion reasons and make the scan incomplete/HOLD; they are not silently skipped while reporting a complete total. This is structural validation of pinned repository artifacts. It does not independently query or re-authenticate external workflow runs, owner comments, or upstream repositories at report time.

## Frozen inputs

- all295_execution_disposition.json: blob f5c45dc8919b1b800e89a421676a3627e75fb3bb
- work_receipts.json: blob 6a9c71393735dbc4b5c1577272f22cef38ab6338
- Dispatcher status test asserts 295 registry entries do not mean 295 accepted tasks: test_owner_catalog_progress.py, blob fea214f4e5ced3252adcce5788d3eb54884bcf71

This note changes no original acceptance state.