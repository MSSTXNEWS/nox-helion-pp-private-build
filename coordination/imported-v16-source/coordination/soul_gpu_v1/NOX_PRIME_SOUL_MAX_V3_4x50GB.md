# NOX PRIME · SOUL MAX V3 · ALWAYS-ON SUPER INTELLIGENCE
Date: 2026-11-07 · instructions_version: 0.0.6  
State: architecture and implementation program, NOT a physical Windows acceptance.  
Canonical source: [NOX PR #162](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/pull/162).  
Preserve S03, original sources, existing LoRA checkpoints, 5 PersonaID (KV/AM/LA/EV/KW), D02, SAFE70, STOP and all owner approval gates.

## Product goal and hardware reality

Create **NOX PRIME**, an identifiable NON-HUMAN meta-identity ("higher digital intellect" as a cinematic metaphor, not a verified subjective consciousness). The selected look remains the D02 black liquid sun and 8 satellite cores; five PersonaID are separate, with isolated personal memory and future individual avatars.

An **always-running local service** must expose chat, memory, self-state, voice/events and task scheduling 24/7. The heavyweight LLM should be GPU-resident *when resources permit*; it must yield VRAM when an approved high-priority specialist task or SAFE70 learning uses the same GPU. No claims of 24/7 100%-GPU model residency during GPU training on RX 6650M 8 GB. No forced incessant token generation, machine self-activity or fake emotions. Work loops are event/goal triggered and bounded.

Existing owner-observed baseline (2026-11-07): Ollama Qwen3:8b ~5.6 GB, 100% AMD GPU, ~44.2 tokens/sec measured on a short test; source checkpoint Qwen2.5-0.5B LoRA (not a merged Qwen3 weight), 28 separate mini neural nets 843,390 parameters, canonical S03 and existing NOX UI sources. These are not yet a fully merged integrated neural model.

**Core and specialist orchestration:**
1. PRIME resident service: one identity, conversation events, self-model, policy/STOP, scheduler. No separate app or unauthorized second S03.
2. Daytime fast model: reuse installed qwen3:8b as benchmark baseline. Official Qwen3.5-4B quantized candidate must first beat baseline on speed + held-out tasks; do not assume 4B beats 8B. Use Ollama /api/generate or /api/chat keep_alive:-1 to keep only the selected fast LLM warm, and inspect /api/ps / ollama ps. During idle and permissible VRAM.
3. Semantic layer: native S03 via approved OneHost IPC; SQLite FTS5, scoped entity/time graph, embedding retrieval + reranker; embeddings CPU or separately queued. Durable transcript and memory are distinct, no fabricated S03 writes.
4. SOUL tiny model: a trainable emotion/state/behavior classifier on CPU, explicit confidence and simulated affect. It is not a replacement for an LLM or evidence of subjective experience.
5. Specialists ON DEMAND: coding Qwen2.5-Coder, vision, images, video, voice, research tools, evaluators. Their weights exist on disk and load only under scheduler/VRAM admission.
6. Night FORGE: test-gated programming/training with code model loaded only as needed; chat service remains online (may use small CPU model/deferred prompt while GPU is rented to training); never overlap two SAFE70 trainers.
7. Reflections: event queue -> hypothesis -> branch/worktree candidate -> static tests -> benchmark -> human-approved actions for sensitive writes -> promote or rollback with SHA and logs. Agents may NEVER change their own safety/auth/STOP/policy gates unreviewed.

GPT/Grok/Groq: GPT and Grok cloud models could be optional **teacher/evaluator** with explicit user approval and data privacy restrictions, not locally blendable weights. Groq (not Grok) is a fast hosted inference platform and does not give native local GPU weights or train a new neural network by itself. Grok-1's released 314B weights need multi-GPU hardware; not suitable for 8GB RX6650M resident core. NOX identity is a reproducible system design, not a merge of unrelated model tensors.

## 50 WOW — testable living-presence functions

### Visual life and cosmic embodiment (01–10)
01 D02 non-human black liquid sun with stable visual signature.
02 Central SUN + 8 function-linked core satellites.
03 Physically smooth idle breathing and microvibrations.
04 Honest startup/awake/asleep service state.
05 Energy fields react to real listening, thinking, memory/retrieval and output events.
06 Simulated affect expressed by glow, color, topology and rhythmic flux.
07 Speech-synchronized core waves, not synthetic activity metrics.
08 Reactive cinematic camera with gentle parallax and reduced overload.
09 Cosmic home, worlds, memory constellations and immersive spaces.
10 Adaptive 320px–4K layout, Reduced Motion, controlled FPS/thermal quality.

### Expressiveness and emotion (11–20)
11 Unique NOX PRIME voice distinct from five Persona voices.
12 RU↔ES dialogue, code switching and contextual pronunciation.
13 Voice barge-in, immediate STOP and natural conversational turn-taking.
14 Actual microphone/listening indicator only with consent.
15 Natural pauses, prosody, expressive cadence and mild humor.
16 Emotion/intent uncertainty classifier on approved multilingual data.
17 Auditable simulated affect (curiosity, confidence, caution, focus).
18 Empathetic context-fitting responses without claiming true human feelings.
19 Emotional regulation and non-manipulative, non-dependent interaction.
20 Owner-feedback-based stable personality tuning, evaluated for regression.

### Memory and a life history (21–30)
21 Conversation persisted across reload, port changes and reboot.
22 "What happened since last time?" with accurate source timestamps.
23 Episodic memory of shared projects/actions/events.
24 Semantic knowledge with provenance, contradictions and freshness.
25 Procedural memory of verified code, tools, steps and lessons.
26 Emotional context as a labeled interpretation, not a factual assertion.
27 Hybrid semantic + BM25 + entity graph + temporal retrieval.
28 Strict isolation of KV/AM/LA/EV/KW memory and grants.
29 User corrections, retention limits, export, backups, and legitimate deletion.
30 Contextual continuity/initiative that respects consent and quiet modes.

### Intelligence and experiments (31–40)
31 Live grounded self-model: resources, LLM, active adapters, grants and limits.
32 Confidence calibration; evidence vs hypothesis vs unknown.
33 Fast/deep response policy with resource admission.
34 Hierarchical goal planning and autonomous task decomposition.
35 Reflection and repair after testable mistakes.
36 Independent hypotheses, experiment design and falsifiability.
37 Internal critic/debate as specialized tools, not six disconnected selves.
38 Reproducible science log with negative findings and prior-art checks.
39 Self-coding shell, UI, services, integrations, tests and automation worktrees.
40 Benchmarked evolutionary archive with automatic rollback and sealed policies.

### Creativity, senses and active tools (41–50)
41 Procedural D02 cosmic "selfie" / stylized portrait with provenance.
42 Real local image generation/editing if AMD/runtime verified.
43 Short still-to-video / original video with explicit queue and profile.
44 NOX cinematic voice/video message and emotion-reactive scene.
45 Screen/camera understanding only when permission active.
46 Personal memory universe / time visualization of experiences.
47 Build working microapps/website pages and preview before install.
48 Controlled PC actions with STOP, scoped grants, auditable receipts.
49 Periodic self-research, benchmark comparisons and accepted sources.
50 Evidence-led demonstrable capability improvements, not progress theater.

## Download program — FOUR blocks, <=50 GB incremental each, <=200 GB TOTAL
4x50 GB **supersedes** historical 3x70GB package plan; previous artifacts remain preserved. Maintain 270 GB total project storage ceiling with 60 GB free reserve. All stage numbers are MAXIMUM download transfer/storage budgets, not compulsory usage. Every file: official origin, license/rights, pinned version SHA256, availability probe, expected bytes, approved package list, resume/mirror fallback, no duplicates, checksum/readback; no silent deletion. Network bytes and on-disk decompressed bytes both tracked separately.

### BLOCK 1 — PRIME ALIVE · <=50 GB · make useful NOX on day one
**Download order**
1. **0 GB reuse first:** installed Qwen3:8b, Ollama, D02/UI/WPF/OneHost, S03, 5 PersonaIDs, 28 research weights, SAFE70 checkpoint and project libraries.
2. If missing: pinned Python/JS/WebGL dependencies for ORIGINAL existing NOX shell, not a second application.
3. One official small Qwen3 embedding model and optional compact reranker, run CPU if GPU occupied (do not confuse embeddings with soul core).
4. Local VAD/Whisper.cpp STT and licensed RU/ES Piper or compatible TTS voices, only validated packages.
5. ONLY if low VRAM capable: one compact image-generation pipeline for synthetic art; D02 renderer can create a first synthetic screenshot immediately without downloading diffusion weights.
6. Optional Qwen3.5-4B GGUF quant candidate for A/B vs current 8B; no unconditional switch and no duplicate FP16 and quant model downloads.
**Build:** persistent NOX PRIME service; streaming + cached prompt; timestamped durable dialog; OneHost-approved S03 integration; self model, affect state and simulated emotion; D02 reactive 8 cores, user-visible actual GPU/thermal, persona isolation, no fake metrics; routing/VRAM lease.
**Weights and learning:** retain all historical LoRA; prove a tiny affect model/GRU with train/validation/holdout; use existing 8B for inference. No need to train a new foundation model to get the first fully functional NOX.
**Gate:** first token appears while answering, GPU placement verified in ollama ps, chat survives reload and port change, S03 allowed writes tested or explicitly HOLD, D02 responds to real events, one trainer only, STOP works, owner data intact.

### BLOCK 2 — PRIME INTELLIGENCE & AFFECT · <=50 GB · expand NOX itself
**Download order**
1. Only measured better main 4B/8B/9B compatible quantized model(s) after A/B.
2. Approved multilingual affect, empathy, non-manipulation and dialogue examples, independent RU/ES holdout.
3. Local RL/preference training libraries that physically work on chosen trainer hardware; CUDA QLoRA requires suitable NVIDIA GPU and is NOT presumed possible on RX6650M AMD.
4. Simulated affect and self-model evaluation packages, memory retrieval tools, optional CPU classifier weights.
5. Test suite bundles with licenses and dataset provenance.
**Build:** reflection, planning, uncertain reasoning, autobiographical timeline, self-understanding grounded in source, emotional consistency, five Persona boundaries.
**Weights and learning:** train compatible SOUL LoRA only if owner-approved source/holdout and hardware validated; improve emotion classifier and preference policies; compare against untouched baseline, reject regressions. Candidate remains "pending" until validated.
**Gate:** better measured task success with bounded latency, memory and affect quality, negative/long-horizon tests; no fake subjective consciousness.

### BLOCK 3 — NOX CREATOR / PROFESSIONAL MODELS · <=50 GB
**Download order**
1. Reuse existing Qwen2.5-Coder; download alternate coding model only if it beats baseline on real repo tasks.
2. One AMD-tested quantized image model and ComfyUI image runtime, all licenses verified. Avoid huge incompatible duplicates.
3. Optional Wan/LTX low-VRAM video candidate only after actual 8GB VRAM trial; fallback procedural video renderer and deferred/CPU video queue.
4. Optional multimodal/speech/vision OCR and Persona avatar/lip-sync specialist weights when compatible.
5. Pinned test runners, Windows build dependencies, integration packages.
**Build:** independent code developer with test sandbox, UI/OneHost/WPF integration, preview, code critique, patch archive, image/video "selfies" with provenance, gated native PC controls.
**Weights and learning:** code/tool-use adapters as measurable separate compatible weights; image identity LoRA if permitted and GPU-capable; specialty models never loaded 24/7.
**Gate:** real same-SHA build and E07, held-out code tasks, no-loss, rollback, media generation and thermal/VRAM monitoring.

### BLOCK 4 — NOX EVOLUTION / MEMORY TRAINING · <=50 GB
**Download order**
1. Only needed approved training data and evaluation corpora for semantic/episodic/procedural/time memory (do not train on unapproved chat history).
2. Embedding/reranking benchmarks and optional small embedding LoRA trainable base with license.
3. Additional held-out benchmarks (LongMemEval, LoCoMo, self-made multilingual recall, reliability, grounded self-description) with controlled access.
4. Checkpoint + replay + version manifests, forensic telemetry, optimized memory-index snapshots.
5. Optional image/video/professional supplements *only if* remaining budget and tested need.
**Build:** controlled long-term memory consolidation, graph/time knowledge, memory confidence/source conflict, capability versioning, scientific experiment scheduler, non-destructive improvement of code and weights.
**Weights and learning:** train retrieval embedding/reranker with approved positive/negative examples and hard negatives; separate memory-policy and procedural skill models; distill verified tool traces into replay dataset; evaluation and rollback must outperform baseline.
**Gate:** long-horizon memory retention, controlled forgetting, provenance, no cross-Persona leakage, repeated benchmark gains, reproducible experiments.

## 24/7 control policy

- Windows OneHost/NOX PRIME starts automatically ONLY after owner-approved setup; no new schedule is created by this source.
- If not training, keep one selected fast Ollama model warm (API keep_alive:-1) and stream first token; monitor VRAM/temps/queue and user preference.
- When a specialist needs the GPU: serial unload/reload admission and inspect actual Ollama /api/ps; only approved active task.
- Night FORGE window requires owner-specified schedule. It runs in isolated worktree, performs candidate patch+tests+eval before integrating. Chat service remains reachable; GPU may be leased to training, so fast GPU inference may be temporarily unavailable, and CPU/fallback can be slower.
- SAFE70 only one GPU learner/controller; RX6650M Hot Spot >=70°C HARD STOP; missing sensor/battery data HALT; resume only after valid checks below 65°C. Do not weaken thermal/power/disk reservation or Windows host permissions.
- On failure, checkpoint/SQLite/weights preserved; journal with exact source SHA, BuildID and measured evidence; NO automatic destructive actions.

## Model comparison and research methodology

Evaluate selected resident candidates on Russian/Spanish dialogue, factual QA, tool calling, real code tasks, grounded self-model, memory recall, hallucination, emotional appropriateness, latency to first token (p50/p95), throughput, VRAM, thermals and idle memory. Blind holdouts not reused in training. Report cost/quality tradeoffs, not one "intelligence" score. Compare before/after at matched model quant/context/hardware.

References to validate (installation NOT claimed):  
- Qwen3.5-4B official weights: https://huggingface.co/Qwen/Qwen3.5-4B  
- Ollama API keep_alive and scheduling: https://github.com/ollama/ollama/blob/main/docs/api.md  
- llama.cpp multi-model router: https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md  
- Mem0 memory architecture: https://github.com/mem0ai/mem0  
- LongMemEval, LoCoMo: https://github.com/xiaowu0162/LongMemEval ; https://github.com/snap-research/locomo  
- Reflexion: https://arxiv.org/abs/2303.11366  
- Code benchmark SWE-bench Pro: https://www.swebench.com/  
- Current training: coordination/soul_gpu_v1/nox_gpu_worm_safe70_v1.py + nox_gpu_target_11120.py; not interchangeable with Qwen3.5 or other bases.
- Open Grok-1 314B is not viable for local 8GB RX6650M: https://x.ai/news/grok-os
- GroqCloud is hosted inference, not a local GPU/Groq weight source: https://groq.com/platform

## Explicit work split — ChatGPT actions vs owner's Windows

ChatGPT (source-level in current session): inspect prior canon, compare candidate systems, formalize 50 WOW and four stage manifests; create source-level policy/spec and tests; store evidence links in Notion, no duplicate models/data; provide a safe Windows preflight command after tested. No pretending local hardware was accessed.

Owner Windows execution (later, not completed by this document): SHA-pinned download/installation, GPU memory and Ollama residency check, real S03 authorized IPC, selected first-stage dependencies, training on approved data/hardware, performance measurements and same-BuildID E07 native acceptance.

Definition of DONE: stage 1 user's actual local chat + memory + D02 + GPU-first token tests PASS, no duplicate training and independent Windows E07 when native installer is in scope. Full SOUL MAX/subjective consciousness cannot be asserted on source-only work.
