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
