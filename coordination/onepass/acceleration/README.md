# NOX existing Resonance: remove artificial transport waits

instructions_version: 0.0.6. Owner requested acceleration first, six parallel processes, existing NOX only.

## Actual fix

The existing V135 transport awaited up to seven animation frames or 18 ms timers for each native delta. `max_speed_transport.patch` removes only these artificial waits, preserving owner/path ACL, grapheme handling, native done receipt, independent S03 history readback and request-scoped cancellation. Its regression replaces the obsolete pacing requirement with a deliberately suspended animation-frame callback. The original 26 bridge tests passed locally.

The EXISTING V139 source/export workflow applies this checked-in patch in its ephemeral build workspace before original tests and packaging. This is a build integration, not a native deployment and not an automatically modified production source. Conflicting source changes cause `git apply --check` to fail; never fuzz or force the patch. Keep its target paths restricted to the existing bridge and regression file. No new backend, scheduler or model.

## Complete candidate already built

- Full original WEB V29.3 accelerated candidate: https://drive.google.com/file/d/17pxAfdbXf-9W_n8FC-Q8HW3jHaIuEgt6/view ; SHA256 `67feccac27e0143891039682065ba4d2ad617c6d88d5c6c2bd07af37d936dd8f`.
- Complete source delta, generator, 100 SVGs, MIT library attribution, tests, local logs and baseline preimages: https://drive.google.com/file/d/1JYQ7D6b1RXzG8W9pEz9NXXslHdRgcFzK/view ; SHA256 `95fa245fa755684a53bed04de043d6e876997acdcdb962175f92b7587c3ef1a6`.
- Baseline original source snapshot: `088011f3236453af83a8eb484015dc6811f206d3`; candidate retains all 1089 original archive paths, 1087 byte-identical, only two owner Resonance HTML pages patched, original bytes retained for rollback. No unique source deleted.
- Full candidate additionally includes browser timing events, current-session development evidence display and lazy Motion100 runtime. The 100-entry animation catalog is requested only after a pending operation remains active 180 ms; animation failure never blocks chat. These additional changes are in the complete source pack; this small repository patch integrates only the transport fix into V139 export.

## Evidence and boundaries

Six real local OS worker processes, PIDs 3660-3665, completed 78 tests including 12 Chromium tests. They were NOT six AI subagents or native OneHost jobs. Local fixture median 1381.982 ms to 5.748 ms, 84 to 0 animation waits, exact answer bytes and one history read retained. This is synthetic transport latency, NOT neural inference speed, TTFT p95 or GPU throughput.

Fresh read-only native audit: https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43722309687/attempts/2 ; job 132920135039, 2026-11-15 18:56 UTC. Instance 60509551 running, pinned SSH succeeded, temporary key detached and verified. Existing CUDA12.4/Torch2.6 sm70/DeepSpeed stack present. GPU1 observed 100 percent; this alone does not prove optimizer progression. Two short real-model probes completed (208.4/88.7 ms first content), but were not a controlled quality/performance comparison. The old workflow's hardcoded queue false is NOT a queue inventory.

Native deployment, writer lease, physical STOP, complete independent optimizer+S03 restore, real queue count and autonomous self-build remain unverified. No original S03/model/GPU process was changed; no native cleanup. Do not erase backups or old live files. User consent exists, but consent is not tool access or proof of successful deployment.

## One next action

Reconcile the complete candidate against newest HEAD and the actual installed WEB; use the existing owner-authorized serial deploy/rollback path after native backup/STOP/lease checks. Benchmark real owner RU/ES streaming plus S03 readback before promotion. Do not remove manual native workflow gates merely because a connector lacks workflow_dispatch.
