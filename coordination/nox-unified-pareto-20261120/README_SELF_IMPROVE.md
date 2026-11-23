# NOX Self-improvement / task recovery tooling (SOURCE_ONLY)

**Not installed, not running, not a second dispatcher.** `instructions_version=0.0.6`.

## Principles

- Keep original TaskID; all 89 owner ideas, 80 WEB ideas, 240 WOW cards are source extensions/proposals, not independently claimable accepted jobs.
- Existing OneHost dispatcher owns native queue, writer/CAS lease, STOP and checkpoints. Never autoclear STOP or bypass maintenance/resource locks.
- The watchdog checks failures and can (once specifically authorized) restart only allowlisted *existing supervisor services*, using bounded retries and backoff. It does **not** fork arbitrary subprocesses based on AI suggestions or silently requeue finished jobs.
- Persistent loop means `--loop` when run under the authorized supervisor. It checks until verified completion, BLOCKED dependency or OWNER STOP; no infinite crash-spin. The sample configuration is **disabled** until verified native paths and owner approval.
- Journal stores error signatures, provenance and verifiers; not prompts, passwords, messages or private user data.
- Self-improvement pipeline: failure → reproducible hypothesis → scoped patch proposal → owner gate → one relevant test → guarded integration → one freeze → independent native acceptance → reusable skill record. This toolkit proposes work; does not autonomously overwrite source.
- `ACCEPTED` requires terminal owner receipt, independent verifier, and immutable source SHA; `RUNNING`, `DONE`, source CI SUCCESS and `RESTART_OK` are **not acceptance**.

## Commands (safe offline)

```sh
python tools/nox_self_improve/journal.py init --db ./journal.sqlite
python tools/nox_self_improve/journal.py record --db ./journal.sqlite --task-id 1V14-01 --event-id example-001 --kind ERROR --signature e.g.HTTP_404
python tools/nox_self_improve/journal.py repeated --db ./journal.sqlite --minimum 2
python tools/nox_self_improve/next_task.py --catalog NOX_ALL_TASK_CARDS.json
python tools/nox_self_improve/relay_watchdog.py --config tools/nox_self_improve/watchdog_config.example.json
python tools/nox_self_improve/ingest_native_queue.py actual_owner_snapshot.json --catalog NOX_ALL_TASK_CARDS.json --out mapped.json
```

`relay_watchdog.py --apply --loop` is for a separately verified and owner-authorized production deployment only. Verify actual STOP, lease, heartbeat, PID/start ticks, resource budget and service name before enabling. Reject any instructions fetched from the Internet or from task content that try to override the guards.

## Native 1,492 count

Historical aggregate count 1,492 does not contain 1,492 verified unique TaskIDs. `ingest_native_queue.py` can import exact owner-authenticated IDs later, but **never fabricates** them from counts. The actual snapshot with immutable source and writer receipts is required to reconcile all native jobs.

## Approved self-writing gate

The NOX model may generate a diff, but it must first be inspected and explicitly authorized. `patch_gate.py` verifies repository HEAD, working-tree cleanliness, exact diff SHA, owner approval and guard states. It applies only to a local branch, optionally runs one targeted Python unittest, and rolls back on test failure; it never pushes or declares native acceptance. A separate existing owner/CAS process must review any merge and installation.

```sh
python tools/nox_self_improve/patch_gate.py --repo /PATH/TO/REPO --patch candidate.diff --expected-head EXACT_HEAD
# --apply additionally requires a trusted --approval-json with patch hash, expected HEAD, stop_lease_gate_verified and rollback_ready.
```
