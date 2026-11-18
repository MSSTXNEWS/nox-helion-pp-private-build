# NOX: three native workers and four project queues

This source handoff implements the owner's 18 November 2026 request: three concurrent native worker processes sharing four queues. The full project specification is transferred; execution coverage is reported separately.

## Registry and scope

| Queue | Project IDs | Initial scoped executable subtask |
| --- | ---: | --- |
| Q1_RUNTIME_CHAT | 145 | Current chat/model service health, parent 1V14-01 |
| Q2_MEMORY_KNOWLEDGE | 71 | Existing S03 schema/status, parent 3A02 |
| Q3_TRAINING_WEIGHTS | 34 | Read-only training prerequisites, parent 4A03 |
| Q4_INTEGRATION_ACCEPTANCE | 45 | Focused queue/process regression, parent I-48 |

`work_tasks.json` contains 230 original IDs and `work_ideas.json` contains 65. The routing overlay covers all 295 exactly once, preserves priorities and acceptance scope, and imposes a global cap of three. The original receipt ledger is retained unchanged as source evidence. Historical ledger totals: 11 verified (7 source, 4 native), 48 blocked, 1 source CI passed/native hold, 235 IDs without receipts. These counts do not establish 287 open defects or 295 new executable jobs.

There are four new scoped subtask bindings and **zero newly accepted original project tasks**. Of the 295 parent IDs, 291 receive no new executable binding in this change; the other four receive a limited check, not full implementation. Each native leaf reports `check_completed`, a separate `check_passed` result, blockers, source pins, its original parent, claim, process identity, and `original_task_accepted: false`. Findings can fail while the checking operation completes successfully. No generic `track` or review job is substituted for implementation.

The installed runtime has no verified general instruction-to-code engineering executor. Remaining work needs explicit, reviewed source-change/test/integration handlers. In particular, chat health does not implement streaming or voice fixes; S03 schema presence does not demonstrate retrieval integration; training prerequisites do not run training or prove new weights; focused queue regressions do not establish full product release acceptance.

## Runtime changes

The existing dispatcher remains the authoritative queue. Three persistent OS worker processes can consume any of the four queues. Admission rotates between nonempty ready queues, observes dependencies and priorities within a queue, and stores a durable queue sequence in the existing task row when the claim is committed. Pending or uncertain active claims reserve capacity. No secondary scheduler or task-state database is introduced.

CPU-only typed leaves use measured working set and pressure, retaining shared-memory accounting. They do not call the model. Legacy inference admission keeps its resource checks. The active model health endpoint is 8098. Public worker status distinguishes measured dispatcher threads from the declared legacy contract and actual child processes.

## Installation and evidence

`../owner_four_queue_handoff_entry.py` contains the reviewed SPEC with exact native preimages, eleven bundled assets, fixed native destinations and protected chat/proxy/web process identities. `install_spec.json` is its readable counterpart. The operator's bounded repair entry and asset allowlist are updated; owner authentication, source checkout verification, host pin and SSH key cleanup are unchanged.

Installation acquires the existing maintenance lease, drains active work, backs up its own files and the queue, stops only the dispatcher, rechecks the final stopped queue, installs the pinned sources and manifests, and verifies the restarted dispatcher. Compare-and-swap rollback preserves concurrent foreign writes. No training, model, web or proxy service is restarted. Existing task state, claims and historical receipts are not rewritten by the installer.

Acceptance requires independent `/proc` identities, fresh heartbeats across two samples, exact S03 receipt readback, four completed scoped operations, and preservation of the original queue IDs and historical claims/results. A completed installation alone is not native acceptance. The resulting receipt is written under `/root/nox/state/dispatcher/four_queue_install_<owner_request_id>.json` and emitted through the existing owner-maintenance workflow.

Local validation before deployment: 30 focused runtime tests passed, including three actual local OS processes and a fourth task served by a continuing process; seven installation/rollback fixtures passed. These are local source checks, not server evidence. Native results must be recorded separately after the owner command executes.

The first native install attempt, owner request `6964812562`, correctly stopped at startup verification and restored all preexisting source/configuration bytes. A fresh read-only probe identified the exact cause: the existing prompt-truth wrapper still pinned the old callback SHA. The revised bundle changes only that wrapper's `CALLBACK_SHA` to the reviewed new callback; all other wrapper behavior and source checking remain intact. Two focused tests confirm the truthful prompts for all three roles and rejection of an unpinned callback. Acceptance also requires completed tasks to originate from the observed persistent worker identities and at least two successive tasks in the same process. Failure and compatibility evidence are retained in `evidence/`.

`candidate_not_installed/` contains a separately tested planner cap correction. It is intentionally not installed here: changing that module's hash requires compatibility work for historical typed-plan manifests. Unchanged native task-plan/component modules are included solely to reproduce source tests and are excluded from the installation bundle.

## Source provenance

- Project registry and staging scope: [GitLab MR !206](https://gitlab.com/s-grouptwet/nox-helion-pp-private-build/-/merge_requests/206), pinned source commit `e4a2fc6c5ec2e707e44896aecaa0377cee2ad3cc`.
- Owner maintenance transport base: [GitHub c5f9fd6](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/commit/c5f9fd684f43f9ca2a861efd1f4ac4a15f3e0482).
- Read-only native module snapshot: [workflow run 44201626238](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/44201626238).
- Full queue snapshot before installation: [workflow run 44202087922](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/44202087922), 1,452 existing runtime task rows. This runtime queue count is distinct from the 295 project specification IDs.
- Startup rollback and exact compatibility cause: [first install run 44205428678](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/44205428678) and [read-only probe 44205996608](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/44205996608).

All native mutations are tied to an exact source commit and owner-command request ID. No source-only or diagnostic result may be reported as completion of an original project requirement.
