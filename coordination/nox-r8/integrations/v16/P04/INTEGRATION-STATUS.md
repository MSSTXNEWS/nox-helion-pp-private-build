# P04 integration status

Status: source candidate staged for review; runtime integration is not complete.

## Seven work tracks

1. RAG retrieval, embeddings, citations, update/delete, and bounded chat context.
2. Safe local text/Markdown ingestion with provenance and strict limits.
3. Real Transformers/PEFT QLoRA training with explicit rights and model gates.
4. GPU sensor telemetry, serialized work queue, and ECO/BALANCED/INTENSIVE pacing.
5. Versioned P04-to-P05 event and report projection contract.
6. Integration boundaries, dependency compatibility ranges, and source-builder notes.
7. Coordinator integration review, checkpoint/receipt integrity review, SHA inventory, and PR packaging.

## Ten coordinator review approaches

1. Confirm the exact base commit and candidate branch before writing.
2. Check every candidate path is regular source text and inspect the inventory.
3. Recompute SHA-256 for every candidate file and compare agent-reported hashes.
4. Check RAG core and ingestion method signatures are aligned.
5. Check training authorization, model identity, and local-only data/model gates.
6. Check the training worker uses real Trainer callbacks and reports actual loss values.
7. Check pause/resume and checkpoint identity are bound to the same run inputs.
8. Check adapter merge requires a completed receipt, exact base identity, and a fresh output path.
9. Check GPU telemetry can be unavailable, policies only pace work, and no unsupported hardware power cap is claimed.
10. Check P05 evidence remains unverified until independently validated and disclose missing installer/source-freeze integration.

## Verification boundary

These are source-level reviews only. No tests, builds, dependency installation, model downloads, dataset processing, GPU training, evaluation run, or checkpoint generation were performed. A real checkpoint remains HOLD until the host supplies an approved dataset and verifier attestation, a compatible approved model snapshot, and an available CUDA GPU with required runtime dependencies.

This repository is a Windows candidate builder. The current builder reconstructs a separate source archive and applies locked patches; this candidate package has not been wired into that archive, a project file, the live chat host, or the installer. The draft PR is therefore reviewable source staging, not a release-ready P04 implementation.

## Current run progress — 2026-10-27

Each role completed 10/10 approaches. These bars measure review activity; they do not measure accepted product requirements.

- RAG / embeddings / chat seam: `[██████████] 10/10 approaches` · source candidate 3/3 files · live host integration 0/3.
- Approved dataset preparation: `[██████████] 10/10 approaches` · fail-closed verifier contract in worker · trusted verifier/data not supplied · runtime 0/1.
- PEFT / safe merge: `[██████████] 10/10 approaches` · v2 receipt and rights re-attestation source aligned · merge execution 0/1.
- QLoRA / Transformers: `[██████████] 10/10 approaches` · trainer emits typed losses and HOLDs on invalid evaluation receipt · training/checkpoint 0/1.
- GPU / NVML Guardian: `[██████████] 10/10 approaches` · telemetry/event fields and queue disposal fix in candidate · live sensors 0/1.
- Checkpoints / evaluation / P05: `[██████████] 10/10 approaches` · v3 event/report candidate aligned · live event delivery 0/1.
- Coordinator integration: `[██████████] 10/10 approaches` · reconciled receipt v2, typed metrics, sensor telemetry, report and SHA ledger.

Overall activity: `[██████████] 70/70 approaches (100%)`. Product integration: `[░░░░░░░░░░] 0% accepted`; runtime acceptance is unverified and remains HOLD. No checkpoint exists.

### Ten coordinator approaches for this run

1. Read the latest shared error/self-improvement journal and exact P04 report tail.
2. Apply the recent journal rule: compare candidate source, runtime integration, and acceptance separately.
3. Dispatch six non-overlapping roles plus the coordinator; keep tests, builds, installs, downloads, training, and outreach out of scope.
4. Search the Windows runner and release-staging repositories for exact RAG/chat host source; found no safe source preimage.
5. Inspect the canonical builder entry point and confirm its archive, tree, and patch chain are locked.
6. Compare worker and merge contracts; align merge to receipt v2, receipt dataset field names, and exact rights attestation hash.
7. Align the v3 P05 schema with real typed train/evaluation metric fields and actual nullable GPU sensor fields.
8. Add the authenticated chat-context provider seam without claiming a live host connection.
9. Recompute each candidate file SHA-256 and prepare role/overall progress bars with HOLD status.
10. Append the new run to the P04 report and shared journal using revision guards; read both back by exact RunID.
