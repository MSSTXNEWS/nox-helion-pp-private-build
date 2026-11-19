# NOX project execution adapter

This package connects real source edits to the existing sole dispatcher and its
three persistent OS workers. It creates neither a scheduler nor a second queue.
The existing owner claim nonce, STOP, maintenance lock, writer lease, S03 and
four-queue admission policy remain authoritative.

## Execution boundary

`owner_native_project_work` accepts one of two reviewed catalog references:

```json
{"parent_task_id":"3A02","plan_sha256":"<64 lowercase hex>"}
```

```json
{"parent_task_id":"1A03","contract_sha256":"<64 lowercase hex>"}
```

The row's `source_sha256` pins the installed `owner_subagent_dispatcher.py`.
The second form invokes the separately pinned planner, model client and bridge.
Model output cannot choose commands, test modules, source roots or acceptance.
The parent validates the generated content-addressed plan against that exact
contract before integrating any file.

Workers stage exact source context in a private attempt directory, apply pinned
payloads there and run the fixed unittest verifier. They never change the shared
project root or authoritative queue. The native parent integrates only a
successful prepared result, holding its current claim, the queue writer lock and
a project-root integration lock. It compares every pinned source preimage,
backs up changed files, journals before writing, atomically replaces each file
and verifies postimages. Source roots are explicitly `SOURCE_WORKSPACE`; live
service deployment and original-task acceptance are separate actions.

The six reviewed plan fixtures and the model challenge are integration inputs,
not a claim that all 295 original requirements are executable or accepted.

## Artifacts and API

The owner configuration embeds `project_executor` with schema
`NOX_PROJECT_EXECUTOR_CONFIG_V1`, `enabled=true`, `max_workers=3`, trusted
`roots`, `package_root`, `state_root`, `sandbox`, and exact `source_pins` for
the executor and verifier. Native module pins additionally cover
`owner_project_native.py`. Model configuration independently pins all three
planner/client/bridge files.

The package layout is content addressed:

- `plans/<sha256>.json`: exact `NOX_PROJECT_WORK_PLAN_V1` plans.
- `blobs/<sha256>`: full file postimages.
- `contracts/<sha256>.json`: trusted planner contracts.
- The optional dependency manifest pins each copied third-party file and its
  approved preload module list; it is not chosen by a plan or model.

`materialize_plan(plan, payloads, config)` validates and publishes immutable
plan/payload objects. For a model candidate, supply the approved contract hash.
`verify_candidate(...)` or `prepare(reference, config, claim, ...)` performs
staging and real isolated tests, returning `PREPARED` or a truthful failure.
`integrate_prepared(reference, config, claim, gate=...)` is parent-only.
`recover_interrupted(...)` performs exact journal/readback recovery without
blindly replaying a shared-source mutation.

Each attempted plan has its own journal under
`attempts/<task digest>/<claim>/<canonical plan digest>/`. Therefore a model can
test, correct and test another candidate under the same native claim. Failed
tests never change the shared source tree. Interrupted partial integration rolls
back only files still equal to the planned postimage; an intervening foreign
edit produces `HOLD_RECOVERY_REQUIRED` and an unknown change state, preserving
the reservation for explicit recovery.

## Isolation

Production uses `chroot_seccomp`: a fixed Python subprocess loads only pinned
trusted dependencies, enters a private filesystem, permanently drops uid/gid,
closes inherited descriptors, applies hard verifier resource limits and installs
a seccomp filter. The filter prohibits external sockets, exec, fork, privileged
operations and cross-process signals/access. Anonymous Unix socket pairs and
threads remain available for local asyncio and concurrency tests. No model
command is executed. Internal filesystem aliases preserve Python package loader
paths inside the new root; they do not expose host directories.

Every verifier invocation tests its own non-root identity, hidden host path,
network/fork/exec denial, no-new-privileges and seccomp state before importing
candidate source. A missing capability yields a blocked result. The local
workspace can exercise the same fixed runner through `bwrap_seccomp`; a native
chroot preflight is still required before installation because the local user
cannot perform the native credential transition.

`-I -S -B` isolates interpreter startup and prevents pre-confinement bytecode
writes. Test discovery must meet the pinned minimum, no test may be skipped,
and tests must actually finish successfully. Reports retain bounded failure
output for the next model correction. Verified test files and source postimages
are rechecked after the verifier exits.

## Queue lifecycle

Pending and running claims consume the shared cap of three. A blocked project
attempt releases capacity only after an exact durable S03 receipt proves that
its worker is inactive and no unresolved source mutation remains. Unknown
receipts, live former workers and uncertain rollback retain their reservation.
The generic mentor cannot silently revive a proved failed plan; a repaired plan
has a new reviewed task identity. Dead-worker startup recovery is bounded and
requires process/claim reconciliation before retry or receipt adoption.

Idle workers are preserved. Project jobs emit a background heartbeat every five
seconds, including while the existing model HTTP call is blocked. Planner work
has a bounded 1,800-second task budget; the model bridge independently permits
only one background model request. The four queue IDs are preserved and the
next admitted task uses a free existing worker. Pool start/close reason and
timestamps are exposed in native status.

Final source-change receipts use
`PROJECT_WORK_INTEGRATED_ORIGINAL_NOT_ACCEPTED`, retain the planner trace and
exact S03 digest, and explicitly set `original_task_accepted=false`,
`live_service_deployed=false`, and `repository_export_required=true`.
No source test is represented as an end-to-end acceptance of a parent task.

## Verified source package

The final local suite passed 44 tests: the original 30 continuity/four-queue/
leaf regressions; eight real confinement, file-CAS and rollback tests; four
native claim/receipt/connected-handler tests; and two exact callback-pin wrapper
tests. The connected test uses real OS workers and real source changes while
representing S03 transport with an exact-receipt fixture. The separate bridge
integration test passed a model-fixture failure/correction through the real
sandbox and parent integration. These are source QA facts, not native execution
evidence.

All six reviewed plans passed strict schema and content-address validation.
The manifest lists exact runtime bytes for the owner's staged native preflight,
atomic source-pin migration and deployment. Existing leaf receipts remain
verify-only under the explicitly listed historical callback source hash.

## Concurrent native update reconciliation

The first guarded installation stopped on its callback preimage check before
changing native files. A concurrent operation had installed callback
`5f134b8b1915851de15318e23885951885ca84d6515ca1e48c56286862830db5`,
adding durable idle-pool recovery and preservation of idle children during an
exclusive maintenance lease. This version was merged against the common
`88af9c11…` base, preserving those features and adapting their claim census and
receipt proof to project work. Explicit STOP still closes the pool.

Seven focused native tests passed after the merge, including actual idle-worker
retirement/replacement after a project receipt without replay, maintenance
retention, explicit STOP and refusal to retire with pending project claims.
Two exact wrapper-pin tests and a real confined missing-dependency diagnostic
test also passed. The earlier 44-test result is retained as pre-rebase evidence,
not relabelled as a full run on the merged bytes. The manifest records both
source parents and the final candidate hashes. The native chroot preflight is
still required before deployment.
