# NOX HELION — IMMUTABLE DISTILLATION CONTRACT / VERSION 2026-11-09
instructions_version: 0.0.6
scope: NOX PRIME / RunPod A5000 + A40
status: Binding project requirement, not a new optional feature.

## Core
One autonomous NOX with owned consolidated weights; teacher models are tools, never user-facing personalities.

## Required cycle, repeat across multiple passes
1. **Teacher**: collect actual model output from teacher A / B / C. Record immutable teacher identity, base/revision, prompt, response, source SHA, time and uncertainty. Synthetic examples are not independently verified facts.
2. **Curate**: deduplicate, preserve provenance, reject malformed/contradictory data, separate training and never-reused holdout.
3. **Train NOX's full, independent weight checkpoint** on curated distillation dataset. Progress is counted ONLY when real train steps update student parameters and checkpoints are durably saved. Generating a JSONL corpus is NOT weight absorption.
4. **Evaluate** held-out knowledge/skills and regression against previous NOX checkpoint (reasoning, memory, RU/ES, code). Reject regressed candidate.
5. **Consolidate** durable full weights into ONE NOX model, log hashes, model configuration, training ancestry and rollback evidence. NO adapters as final artifacts; do not substitute a LoRA file for unified model.
6. **Repeat** with harder/different source examples and reevaluate until evidence-based plateau, safety constraint or user stop; preserve every verified successful checkpoint.

## Machine split
- A5000: existing training must never be fabricated as adapter-free. Any QLoRA process is legacy and must be terminated explicitly (after preserving last completed checkpoint) before claiming pure distillation. A5000 can produce teacher data and CPU-only memory consolidation while next full-weight integration is prepared.
- A40: train/integrate candidate NOX weights if actual CUDA/CPU memory and disk permit; maintain an isolated target path and never overwrite A5000 active checkpoint. 27B and DeepSeek32 teachers may be GPU/CPU-offloaded with resource controls, but don't promise three simultaneous 9B+27B+32B loads fit 48GiB VRAM.
- Both share /workspace; NEVER assume container-local /opt data is persisted or shared.
- Backup to Windows every 5 minutes *while Windows is online*, SHA256 each copy, delete only confirmed safe disposable material; never wipe sources/checkpoints/model shards on assumption.
- Self-model: grounded autobiography, creator-supplied teachers, functional self-monitoring; no claim of verified phenomenal consciousness.

## Explicit prohibitions
- No LoRA/QLoRA adapter as completion of transfer, no "model absorption" claim for copied teacher weights or saved teacher text alone.
- No fictitious PASS, 100% learned, full model merge, consciousness or guaranteed 100% GPU.
- Do not modify or delete primary model checkpoints without independently verified receipt and rollback path.
- No background task claims unless launched or scheduled in a real service.
- No forced GPU stress loads, no indiscriminate cleanup, no stopping RunPod Pod while unverified ephemeral 27B donor exists.

## Capability and limits
Full-weight 9B optimizer training (AdamW) usually requires much more than 24GB VRAM and can exceed 48GB too. Use verified CPU offload / reduced precision / memory budgeting or smaller student if authorized; STOP/HOLD rather than silently switch to adapters. Training corpus and memory can progress even when direct full-weight training is on HOLD; report explicitly which stage is operational.


## Non-negotiable revision — 2026-11-09
- **Only direct full-parameter, multi-pass teacher→NOX training** counts as distillation of knowledge into NOX's neural weights. Teacher text synthesis alone is data acquisition, NOT training or absorption.
- **No adapters at any stage:** explicitly prohibit LoRA, QLoRA, PEFT, IA3, prefix tuning, low-rank adapters, adapter-only checkpoints and presenting a merge of such artifacts as the target architecture. Existing historical adapter checkpoints are read-only recovery artifacts; not authorized training outputs.
- Teacher Qwen3.5-9B (A5000 foundation), Qwen3.5-27B (A40), DeepSeek-R1-Distill-Qwen-32B (A40): their outputs must be attributed; the 9B NOX student must be evaluated and promoted as ONE full checkpoint. On insufficient GPU+CPU RAM for all-parameter optimizer state, record **HOLD**, not silent fallback to adapters.
- Preserve model ancestry, creator-provided teachers, evidence-based self-model, and independent held-out benchmarks. A percentage of GPU utilization is not a learning metric.
- The desired A5000=2 and A40=4 supervised process slots may prepare knowledge, validation, backup, and teacher inference in parallel; only a compatible exclusive-lock full-model trainer may modify/promote student weights.
- Every 5 minutes, **while Windows is online**, copy source/progress to Windows, verify SHA-256 after copy, then and only then consider pruning explicitly safe obsolete *non-active* duplicates. Never delete original, last checkpoint, active trainer input, memory database, or unmerged models. If Windows is offline, HOLD for that destination; don't claim transferred or deleted.
- The RunPod network volume /workspace is shared between both Pods. The A40 container disk and A5000 container disk are ephemeral and NOT shared. A global volume may be used as an additional replica only after mount, capacity, and integrity verification.
- User-approved baseline supersedes historical instructions that mention adapter-based training. Previously queued scripts are not retroactively changed by this document: they require runtime verification.
