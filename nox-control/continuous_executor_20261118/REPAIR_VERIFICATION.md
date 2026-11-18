# NOX execution repair — 2026-11-18

This report records changes verified on original Vast instance **60509551**.
It separates installed execution-runtime repairs, tested project-source work,
repository CI and weight training. A successful maintenance workflow alone is
not evidence that its admitted project task completed.

## Installed execution runtime

The initial installation used exact source commit
[`1d17cf6a5699832b00fc01d26fa55ec0c17f6355`](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/commit/1d17cf6a5699832b00fc01d26fa55ec0c17f6355)
and [native run 44334613561](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/44334613561).
The later fairness recovery used
[`7625ce13633132711a1ee886bfe2c8ddac402537`](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/commit/7625ce13633132711a1ee886bfe2c8ddac402537)
and [native run 44337688743](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/44337688743).

| Installed component | Result | SHA-256 |
| --- | --- | --- |
| `owner_subagent_dispatcher.py` | One atomic worker-status publication includes the native projection. Catalog exhaustion and dependency waits no longer imply acceptance of unfinished parent requirements. | `84c08283fc3e0e0714704b8bf540eaacb979ec6618f8c1920eb5d75062561c6b` |
| `owner_project_planner.py` | Rejects duplicate-key/nonfinite JSON, reuses measured verification only for the identical candidate within a claim, and terminates repeated unchanged actions with an explicit failure receipt. | `e7bc83e4dea75f08ecb4e92fedf6ef98e0620f17c7b3b28ccb4728c6ddda68ac` |
| `owner_project_model_client.py` | Bounded FIFO admission for three PID/start-tick identities in the existing model-slot lock file; one inference flock remains. Per-turn bound is 360 seconds, maximum slot wait 750 seconds, and native overall job budget remains 1800 seconds. | `f3f9762d74b6d75c5470aa8085df24666606433d56fb2324f8ecf225db2adf2f` |

The fairness issue was observed, not inferred only from a unit test: two tasks
had failed with `MODEL_SLOT_BUSY` after about 120 seconds and zero completed
model turns while another worker repeatedly reacquired the slot. Their original
claims, failure receipts and S03 records remain intact. Two distinct retry task
IDs succeeded after the bounded FIFO installation.

Verification includes seven catalog/status tests, 21 planner/client tests,
seven fairness tests including three real processes completing nine turns,
one confined bridge integration test and 11 recovery-installer tests. These
test groups cover different layers and are not a model-quality benchmark.

## Work completed by the native model

All three results below are `INTEGRATED` in the existing project source
workspace. The exact receipts were independently read from S03, matched to
the claims and current source hashes, and retained in `native_receipts`.

| Task | Model turns | Native tests | S03 item |
| --- | ---: | ---: | --- |
| `3A03.project.cache_limit_contract.20261118` | 4 | 16 PASS | `S03-6d102e85adab47d1` |
| `6V14-12.project.readonly_transient_retry.slot_retry.20261118` | 4 | 18 PASS | `S03-e3d506f9f6f44a99` |
| `4A02.project.bilingual_task_matrix.slot_retry.20261118` | 5 | 39 PASS | `S03-dcb5282cee714fc6` |

Total: **73 native tests passed**, with zero failures, errors or skips. The
model-generated source bytes are preserved under
`native_receipts/model_generated_sources/<sha256>.py`:

| Native project path | Verified postimage SHA-256 | Receipt SHA-256 |
| --- | --- | --- |
| `nox_runpod/teacher_mesh/v38/durable_runtime.py` | `f20917432ddfbedd2287d6894a94ed0fdbe1309d88c64490be47d1bdcedca006` | `51e4581aa76528f832c5c27471d119eccff859f30f2eefa027db7c0416b82c3d` |
| `owner_dispatcher_mentor.py` | `65553f8923a6871f19fc67fb38575897260ab0e74f66bd6ed5e267c5cc8043f8` | `fd2c5ce088364e2f8f2a8a854149a764dcde383380129b3718fb7cbcea802dd3` |
| `forge_split_guard.py` | `cfecaba18466b6a4c6cab6745b1a718bd95b7b2ee87fdb02d26df7e51b630838` | `cc3fdacf5c0e236a82839f9ff86f8b6106910269b60b3b9175cf0f33d2c879ad` |

The cache change rejects invalid limits before native memory recall or cache
aliasing. The mentor change retries bounded transient read-only checks without
escalating them to a senior model. The data-split change requires every
language/task pair separately in train, development and holdout sets.

Evidence: [first result](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/44335372881),
[both fairness retries](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/44339494089),
[full source export and preservation recheck](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/44341781854).

## C02 capacity task and preserved failed attempt

[Admission run 44342326602](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/44342326602)
installed two immutable test modules and one model contract. It changed no
runtime modules and preserved 19 existing terminal project receipts. The new
task was `3A01.project.c02_memory_capacity.20261118`.

[Readback 44345381616](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/44345381616)
verified a failed model attempt: `PLANNER_REPEATED_ACTION_NO_PROGRESS`, ten
read actions, no patch and no test action, elapsed 608882 ms. The planner's
loop termination worked; this is **not** a successful C02 repair. Its source
remained `8657ad367e6dd25b48ca8d6d7c4a947c0e1b0d4b979d63fbdaaf2a8e9ba5e74c`.

The original claim nonce is `724c94a7150fa8f9415e0a28`, receipt SHA-256
`399e3dc5f153ac8832dfb41d74fead6b30f76f2be5257820af39a6e86dea7599`,
and exact S03 item `S03-1460ca0811874a9c`. The immutable test set contains eight
new concurrency cases and 14 unchanged existing cognition/memory test bodies;
baseline has two failures, while the independently reviewed candidate passes
all 22 locally. A separately identified reviewed recovery is being prepared;
it must not be described as model-generated work.

At that readback, all 33 allowed source files were read twice with no change
between reads or unattributed source changes. Census SHA-256 was
`cd8458a5f28420e3281c108e7fd27804aea02c726c10f8793e3e10588a095757`.
Config SHA-256 was
`84b0f78f6d7042b58f6ef003b5bd1ba3423e5244f635dded87b7affd617a3869`.

## Scope and remaining barriers

The installed runtime repairs above are live. The project fixes have the
`SOURCE_PATCH_TESTED` acceptance scope in
`/root/nox/projects/owner_executor/source_workspace`; they are **not evidence
of deployment into serving chat processes**. The native source lineage differs
from several repository paths, so exact postimages are retained as explicit
source artifacts rather than copied over an unrelated repository revision.
Original parent-task acceptance added by this work is **zero**. Catalog
exhaustion must not be presented as completion of the 295 original requirements.

The original chat, proxy and web processes retained their identities during
the runtime installations. The queue can execute admitted reviewed work; it
cannot invent implementation plans for unreviewed catalog entries.

Weight training has **not resumed**. The independently measured barriers are
the existing holdout-regression inhibit latch, stale guard evidence, one sealed
consumer-source mismatch, insufficient raw cgroup RAM and insufficient GPU-1
free memory. The 75 GB anonymous file belongs to the active chat mapping; it is
not abandoned memory. See [TRAINING_RESUME_BLOCKERS.md](TRAINING_RESUME_BLOCKERS.md)
and its linked native diagnostics for exact values and checkpoint limitations.

The repository lifeline CI baseline had 101 passing and 36 failing test
methods because the current inspector omitted APIs used by unchanged tests.
An additive API restoration is undergoing related-suite and privacy review.
Until its actual workflow succeeds, the whole repository CI is not reported
as green. The baseline evidence remains in [CI_BASELINE_STATUS.md](CI_BASELINE_STATUS.md).
