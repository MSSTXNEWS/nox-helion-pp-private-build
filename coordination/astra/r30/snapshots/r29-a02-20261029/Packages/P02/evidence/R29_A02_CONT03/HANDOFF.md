# Astra-A logical A3 / actual root/a02 — continuation03 native frame failure latch

Parent23fc3f054d94fb5ef3f94b5910ab99e91587e1f0. Existing owner branch astra/r29-a02-20261029; old10/10 and prior continuation2/10 preserved. This block makes continuation3/10, not product acceptance. Source maps to R29 A02 approach03/10; canonical product TaskID denominator unknown.

Read before editing: all56 rules/R29 supervisor, historical C34 tail and current master/E06/lesson Docs CONTINUATION-04 directly through connector (read-only; root writes journals). Current role assignment is logical Astra-A/A3 for IPC; /root/a04 owns the original voice-port file separately. This block touches only p02_framed_worker.py and its new test/evidence.

## Actual reproduced failure

The worker recorded a reply write/flush error but continued accepting later requests until input EOF. A deterministic reader waited until the first failed writer/dispatch thread had exited, then supplied a second request. Before fix: two native calls executed and four writes attempted after an incomplete header, followed only later by NATIVE_OUTPUT_TRANSPORT_FAILED. Once framing is corrupt or delivery unknown, a later native action cannot safely rely on that same response channel.

The existing pump now latches output failure on invalid write progress, write exception or flush failure. The same write lock checks the latch before appending bytes; request admission checks before reading, after a blocking frame read and under the active-worker lock; dispatch checks before invoking native code. Already-owned workers retain the existing bounded drain behavior. No new host, queues, process, cancellation authority or transport ownership was introduced. Existing partial-write completion and healthy STOP bypass remain unchanged.

RED: one deterministic test with three failing fault-mode subcases (zero write progress, write exception, flush exception), each showing a second native call after reply failure. GREEN:13 methods including all12 existing frame/short-write/STOP tests and actual OS subprocess stdin/stdout framing. New checks verify exactly one native invocation and no write attempts after the latched failure. No Windows installation/physical-audio/native UI acceptance claim.

Command: PYTHONPATH=Packages/P02/worker-python python -m unittest test_p02_frame_failure_latch_r29.FailureAdmissionTests test_p02_framed_worker.Tests test_p02_framed_worker.PartialWriteTests -v

Boundary: this in-process adapter cannot forcibly interrupt an arbitrary caller-owned BinaryIO.read already blocked at failure time. The host owns pipe closure/read cancellation; when read returns the failed stream cannot admit more work. Existing drain timeout reports NATIVE_WORKER_NOT_DRAINED rather than claiming a still-running operation was cancelled. No undocumented native STOP is synthesized on transport failure.

Remaining scope: native host disconnect/lifetime composition and later Windows same-SHA verification. Original voice-provider boundary is separately assigned to logicalA4; its current file was not rewritten. Known original consent/capture/provider bindings are not invented. No EXE/NSIS/CI/GitLab/finalintegration/main/PR162 change.

Lesson: delivery failure is a connection state transition, not merely a deferred diagnostic. Latch it before releasing worker admission and never append a fresh frame to a stream whose previous frame may be incomplete.
