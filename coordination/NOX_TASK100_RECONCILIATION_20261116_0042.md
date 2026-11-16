# NOX — reconciliation of the old 100-task plan

instructions_version: 0.0.6. Date: 2026-11-16. Review only; no server changes or schedule changes performed by this audit. Last branch metadata read: a7059f0deff8c6236a1b8ba72cb81f1ba3d14af0. Policies/operator code reviewed at 4da75d2df42ba4fa49ca1826837937f04c9ad751. Native evidence cutoff 2026-11-16 00:42:30 UTC / 03:42:30 MSK; diagnostic source SHA 7a998067aae9d5ac86dd3f01a843770277604d38. These are different scopes, not one accepted release.

## Evidence and corrections

- [Current owner hybrid decision](NOX_HYBRID_TRAINING_OWNER_APPROVAL_20261115.md) explicitly supersedes old no-LoRA/no-PEFT/full-only guidance and Windows EXE. WEB29 remains the original UI. Do not treat the pasted old task 82 as a fresh reversal of that decision: this request asks to audit the old list. LoRA/QLoRA -> tested merge -> optional periodic full-base -> measured quantization remains the reviewed policy.
- [Completed native diagnostic 43781890290](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43781890290), job133020728665, verified pinned SSH to exact instance60509551 and temporary key detachment. Dispatcher, priority scheduler and selfheal were RUNNING. This proves observed service state, not successful autonomous work or all60 task registrations.
- Same diagnostic: canonical knowledge.sqlite has 302 s03_items, 302 s03_fts rows, 1598 docs and 3444 chunks. Legacy C01-C08 ltm.sqlite files also exist, some nonempty. M4 absent from populated segment counts does not by itself prove a broken memory layer. Preserve and reconcile legacy records before any deletion.
- Existing BGE embedding endpoint8082 accepted 2 synthetic texts and returned 2 vectors of dimension1024, norms1.0, HTTP200 in0.0626s. No new embedding model was loaded by the probe. This is endpoint functionality, not retrieval-quality acceptance. Do NOT download a duplicate Qwen/E5 embedder by default.
- Legacy FAISS index has 2893 IDs; canonical S03 coverage unproven. 12 possible pinned records can occupy all10 results of legacy chat recall. Fix pin budget and relevant recall before assuming a new base model solves memory.
- sqlite-vec was absent from the inspected interpreter, not necessarily every environment. s03_fts table already exists; verify FTS5 SQL definition and correctness rather than recreate a second lexical store.
- [Earlier actual chat upgrade 43777294443](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43777294443) failed arithmetic and history continuation. Real first meaningful deltas were6551/7222ms, one saved_verified=true; source/runtime installation was rolled back, rollback_verified=true. A later successful diagnostic does not resolve that quality failure. Existing owner status/executor routes rejected anonymous access with401. Six observed native worker IDs are NOT six newly spawned assistant subagents or all60 R60 receipts.
- Storage focus is a candidate inventory with deleted_files0. Its path_sha256 is a pathname digest, NOT model contents/tensor SHA. File sizes/path hashes cannot establish exact HF/GGUF/tokenizer lineage or successful weight training.
- [Primary WEB29 package](https://drive.google.com/file/d/1R9RXZN0FJUJJUq8sJ_n1k3Rh1YcY3R5N/view), 84223045 bytes, and [source patch](https://drive.google.com/file/d/1UhCrgNTCqx51LMB3LLP3ovPgubjwPIYI/view), 215462 bytes, already exist. Source patch SHA256 0ed57b69297bdf07415d1cc9bb50121dfb66ef5dff4c91b84ce9d7a18177b25b rechecked. Full source delivery still needs reconciliation into GitHub; the reviewed delivery site directory contained only dock JS/CSS.
- Local patch rerun: six real overlapping processes1457,1459,1461,1463,1465,1467; lane checks18+13+17+22+8+18=96/96. Scope: SQLite fixtures/offline browser DOM, not native browser/GPU acceptance. 1162 original paths retained;512 cinematic assets unchanged by patch. No new AI subagents claimed.

## Current ordered remaining queue — 32 main outcomes

1. Reconcile complete source patch and current instructions in the shared repository; no overwrite of concurrent work or alternate UI.
2. Refresh bounded native inventory through the existing authorized transport: process/port/model/env/hardware/storage/current writers. Do not re-engineer access already proven.
3. Verify real STOP, owner cookie/ACL, single training writer and per-resource fencing immediately before mutations.
4. Take and independently restore a consistent pre-change backup of original S03/configs/current working model and existing training state. UI rollback is not full optimizer/offsite restore.
5. Produce Installed/Archive/Missing download diff with licences, versions, content hashes and working-space reserve. Download only missing compatible parts.
6. Deploy primary WEB29 progress page/menu and permitted temporary chat dock against actual serving preimages with rollback.
7. Bind self-improvement, knowledge and weight event producers to original S03 and authenticated evolution API, with exact evidence scope/run/time IDs.
8. Bind hourly aggregation to existing dispatcher: stable hour IDs, MSK display, late events, restart catch-up, freshness, filters/details, no fake live values.
9. Fix actual reasoning/arithmetic and server-owned history use; persistent text alone is not successful conversational recall. No hardcoded test answers.
10. Complete genuine SSE and upstream cancel/STOP/abort, full-answer persistence and no placeholder deltas counted as model output.
11. Measure paired RU/ES client TTFT p50/p95, real TPS, quality and concurrency before/after; close first useful chat+memory+STOP acceptance.
12. Verify real WEB29 browser/GPU visuals, all14 controls (6 colors,5 themes,3 modes), D02, original effects, responsive layout, CSP/assets/cache and Reduced Motion.
13. Replace regex-only quick suggestions with context-appropriate NOX-generated suggestions; do not delay main streaming. Keep action authorization separate from generated text.
14. Bind already-approved safe autonomous actions to actual sandboxed tool execution, quotas, idempotency, STOP, tests and outcome receipts; separate new dangerous/external scopes.
15. Reconcile legacy ltm.sqlite memories into canonical S03 with provenance/PersonaID/readback and no loss. Verify roles of M0-M7 and C01-C08.
16. Fix pinned-memory starvation and implement measured lexical+semantic retrieval using existing BGE and s03_fts. Complete one S03 vector index; sqlite-vec/reranker only if needed.
17. Verify source provenance, privacy/PersonaID negative tests, conflict resolution and untrusted web/code/memory handling; no private transcripts silently reused as training data.
18. Ground GENESIS/autobiography/time graph/self-model/skills/reflection/RU-ES tone in verified events within one NOX; no asserted proof of subjective consciousness.
19. Reconcile logical R60 tasks with existing native controllers/workers and callbacks; one controlled queue, no duplicate aliases or new competing scheduler.
20. Admit a bounded first batch <=8 logical jobs within resource slots, validating native job_id, owner, lease, signatures/readback and S03 receipts.
21. Extend to all60 by dependency, prove heartbeat/retry/backoff/dead-letter/orphan behavior and several recovery cycles. Not60 simultaneous processes.
22. Apply measured CPU/cgroup/VRAM/disk/IO limits and background preemption to protect chat p95; optimize useful throughput, not forced100% utilization.
23. Establish exact active GGUF-to-trainable-HF lineage, immutable revision/config/tokenizer/tensor content hashes and licence. Large model download remains conditional.
24. Diagnose and repair the actual current train_error against PID/run/dtype/optimizer evidence; do not repeat an obsolete failed launch.
25. Integrate LoRA FP16 / tested QLoRA and distinct FULL_ZERO3 modes in existing FORGE with mode-locked optimizer/RNG resume and verified trainable parameters.
26. Prepare bounded licensed reviewed data with privacy filtering, dedup and source-separated train/dev/frozen holdout. Guarantee separation from OUR fine-tuning/evaluation-selection, not unknown teacher pretraining.
27. Run one real GPU1 training smoke under STOP/lease and verify optimizer steps, loss/gradients and trained-tensor deltas. Adapter delta is not base-weight delta before merge.
28. Save complete mode-specific model/adapter + optimizer/scheduler/scaler/RNG/checkpoint state and independently restore it; control retention without deleting unacknowledged sole checkpoints.
29. Independently compare quality/retention/privacy and verify unmerged base+adapter vs safely merged isolated same-base candidate.
30. Quantize a validated candidate, measure speed/quality/KV precision separately, promote into the one original chat with draining/readback/rollback.
31. Prove repeated autonomous code, knowledge and weight cycles produce accepted outcomes and truthful three-way hourly reports across restart.
32. Close same-version native WEB/OneHost/S03/STOP/queue/train/restore acceptance (including Windows browser), then remove only exact inactive superseded recoverable copies.

## Conditional later capabilities — not gates for the first useful release

33. Full-parameter distillation when separately measured memory/offload/checkpoint budget permits; not mandatory before first successful LoRA improvement.
34. RU/ES ASR/TTS: reuse present weights and existing Voice Core; test audio/interrupt/licences.
35. PC CONTROL/OCR as needed within approved privileged/privacy scope.
36. Complete release-included pages and CINEMA/STUDIO; optional image/video generation after resource admission.
37. DREAM/replay over verified events, not self-certifying new facts or unauthorized parameter changes.

## Removed/reformulated old assumptions

Old82 no-LoRA: superseded. Old98 Windows EXE: excluded. Old80 globally unseen to every teacher: not verifiable; use a frozen source-separated evaluation protocol. Old37-50 task registration must not be equated with process count. Old95 source preservation must not be called cinematic runtime acceptance. Old87 pathname SHA or any weight change must not be called intelligence gain. All92 API and optional media are not prerequisites for one safe optimizer step. Existing BGE/FTS/controllers must be reused rather than redownloaded/reimplemented.

No exact total progress percentage is derived from this list. Native services and training may change concurrently; refresh time-sensitive data before acting. Complete 100-row task mapping was generated as NOX_PLAN100_AUDIT_20261116.json/.md in this conversation; this document is the concise repository queue and evidence correction, not a deployment receipt.
