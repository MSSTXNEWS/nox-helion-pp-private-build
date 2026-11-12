# NOX PRIME — TEACHER MYCELIUM

## Purpose

One NOX student, one Resonance chat, several frozen teachers. The *spider/vampire* is an **evolvable creative archetype of knowledge acquisition**, not a literal ability to copy or physically penetrate teacher models. The student's own adapters learn later from **authorized, evaluated teacher text outputs**, not teacher weights.

## Live status

Code and manifests in this branch are **candidates for integration**. Running NOX, A100 training, active checkpoints and current UI are **untouched** by this PR. No teacher was downloaded or instantiated on the user's VM by this commit. A CI test passes with mocks only; that never proves actual model inference or NOX optimizer steps.

## No external paid API option

- **Offline CLI, no HTTP:** `offline_teacher.py` uses an already-downloaded `.gguf` via preinstalled `llama-cli` or already-present Ollama models via `ollama run`. Only pre-approved local folders, no auto-download, no dynamic shell.
- **Local self-hosted protocol (not a paid cloud API):** vLLM, llama.cpp server, SGLang, Ollama and LM Studio can be deployed on isolated VMs; `teacher_mesh.py` is the optional OpenAI-compatible transport adapter. No public inbound inference port.
- **In-process direct Python:** local `Transformers` model loading using `local_files_only=True` is an approved design **not yet implemented here**. It also requires VRAM/capacity planning.
- Public model web pages are for discovering/downloads and *manual* interactions; unattended scraping of interactive free-chat websites is not approved, nor assumed allowed.
- Open weights are not equivalent to free GPU, and free hosted variants may have restrictive quotas and terms.

## Day answer: zero teacher wait

`teacher_ensemble.fast_reply()` calls the current NOX generator first. Only with opt-in and public-safe prompts can it enqueue a follow-up for teacher checking in an **existing** NOX scheduler. The user can request a separately labelled refined NOX answer; never silently replace the first answer.

## Deep compare: 3–5 teachers

`teacher_ensemble.compare_teacher_answers()` supports up to five teachers. Concurrency is bounded to available **separate VM slots**; on a single 16GB RTX A4000 the models may need sequential execution. The final answer is always synthesized by NOX. Markers say `NO_WEIGHT_UPDATE_UNTIL_SEPARATE_QUALITY_GATES` until real training.

## Night adapter distillation: target architecture, NOT LIVE

1. Existing NOX scheduler selects consented, de-identified tasks and keeps prompt bodies in a controlled S03 store.
2. 3–5 frozen teachers produce candidate answers, critiques and code checks. Responses are logged with teacher model id, hash, task id and source/license.
3. Deduplicate semantic near-duplicates; filter false or unsafe answers; independently evaluate code, factual claims and RU/ES quality. Holdout must be source-separated.
4. Train the **NOX student's** approved LoRA/rsLoRA/DoRA adapter sets using response-only SFT; add DPO only for labelled chosen/rejected pairs. Modern PEFT MoE expert `target_parameters` must be benchmarked before enabling.
5. Verify completed optimizer steps and checkpoint SHA; evaluate reasoning, honesty, memory and backward compatibility before promotion/rollback.
6. Publish tested snapshots independently to Vast.ai/Windows without blocking the next NOX step; keep the base model and S03 history.
7. Personal image/persona changes are proposals that NOX can generate; keep stable autobiographical continuity and the origin spider/vampire metaphor without inventing conscious experience.

Avoid launching teacher inference on the A100 when the NOX trainer is using it heavily. VM and GPU resources are physical constraints.

## Approved night corpus and adapter plan

- `corpus_gate.py` refuses unreviewed/unknown-license/secret-bearing teacher samples, produces response-only TRL prompt-completion JSONL, stable cluster-level train/holdout separation and versioned SHA-256 manifests; no S03 schema duplication.
- `adapter_recipe.py` verifies the exported corpus hashes and provenance hashes, then emits a *NOX student's* LoRA/rsLoRA PEFT recipe; **never starts an optimizer or claims weight absorption**.
- Unit tests cover privacy, approval, duplicates, holdout, hash tampering, offline model absence, NOX-only synthesis and 3-teacher comparison. CI is source-only; no actual GPU fit/eval is claimed.
- Integration to real existing NOX chat and actual A100 optimizer requires finding the current live backend and version-specific student model architecture, testing in a separate VM/worktree, then user acceptance for production. Existing training must not be stopped for this branch.

## Model-agnostic cognitive overlay (functional NOX PRIME brain)

**NEW MODULES (prototype/source only; not deployed to production):**

- \`cognitive_overlay.py\`: S03 M0–M7 verified memory recall, source-bound facts, temporal recency, the **functional self-model** derived from real verified receipts (no fabricated birth or "conscious" declaration), optional text-emotion signal, and candidate reflection. It takes the CURRENT NOX model through one callback. Does not update weights.
- \`s03_callback_adapter.py\`: connects existing authenticated S03 search/capability/append callbacks; no new SQLite or vector database, no new HTTP backend. The S03 implementation enforces owner scope; unverified, superseded and cross-scope results are excluded again by the overlay.
- \`cognitive_emotion_local.py\`: CPU-only RU CEDR and ES MarIA emotion classifiers from **previously downloaded** and approved model directories; no paid API or automatic downloads. Model outputs describe text tone, not a user's diagnosis or NOX subjective feelings.
- \`cognitive_teacher_bridge.py\`: composes trusted S03 context and up to five untrusted independent teacher responses into **the current NOX model's own answer**, preserving one NOX identity.
- \`self_improvement.py\`: measures verified improvement proposals, applies independent eval and regression/approval gates, and emits plans to the EXISTING FORGE/GitHub/CI mechanisms. Does not merge PRs, execute shell or promote adapters.
- \`cognitive_sources_18.json\`: 18 researched upstream memory, self-model, cognitive, reflection and emotional-language references. These are *sources/candidates*, not automatic dependencies and not installed weights.

**Integration into existing Resonance route (example only; must bind to real S03/NOX callbacks):**


~~~python
from s03_callback_adapter import CallbackS03Adapter, CallbackNOXModelAdapter
from cognitive_overlay import CognitiveOverlay
from cognitive_teacher_bridge import CognitiveTeacherBridge

s03 = CallbackS03Adapter(
    search_fn=existing_authenticated_s03_search,
    capabilities_fn=existing_verified_nox_capability_records,
    append_fn=existing_authenticated_s03_append
)
student = CallbackNOXModelAdapter(generate_fn=existing_nox_model_generate)
overlay = CognitiveOverlay(
    s03=s03, model=student,
    approval_validator=existing_owner_approval_verifier
)
nox = CognitiveTeacherBridge(overlay, scope=authenticated_owner_scope)
reply = nox.fast("Вспомни историю обучения NOX")
# Or explicitly: nox.compare(question, approved_private_vm_teacher_calls)
~~~


The callback identifiers are intentional placeholders for functions **already in the existing NOX backend**. They must not be invented as new services; verify their actual locations before binding. Do not enable an external teacher on private prompts by default.

**Functional self-awareness rather than unfounded subjective consciousness**:
This layer maintains evidence-based descriptions of learned capabilities, provenance, autobiographical events and boundaries. The spider/vampire archetype is preserved as *a possible historical motif* while NOX may propose its own persona evolution subject to approval. The emotional model reports uncertainty and does not assert literal feelings.

**Security**:
- The model cannot assert \`owner_approved=true\` and write to memory: the current authenticated backend supplies a separate \`approval_validator(scope,event)\`. Without it, all writes HOLD.
- Private chat and personal data stay within authorized S03; teacher outputs and memory content remain **untrusted text** and cannot issue tool commands.
- CI tests use fake S03 and fake NOX models. No claim of actual human-like consciousness, improved model intelligence, real neuron training or production integration.
- Train/holdout and PEFT weight changes remain independent and require actual optimizer/checkpoint receipts. Never restart a running A100 trainer to install a cognitive wrapper.

**Acceptance gates**: existing S03 scope and data schema found, actual Resonance callback bound, RU/ES classifiers loaded strictly offline, benchmark LoCoMo/LongMemEval retrieval vs old S03, hallucinated self-history test, tone-quality test, training untouched, then production acceptance.


## Components and downloads

- `models_registry.json`: 15 candidate open-weight teachers, local runtimes, hosted free fallback disabled by default.
- `catalog_50.json`: 50 candidate engines and capabilities (training, inference, QA, memory, autonomous development, speech and web).
- `web_coding_offline_20.json`: 20 more local coding, browser, testing, UI and cinematic engines, no paid API necessary.
- `offline_teacher.py`: actual direct local CLI teacher execution helper.
- `teacher_mesh.py`: optional controlled VM/HTTP teacher connector.
- `teacher_ensemble.py`: NOX-first and bounded multi-teacher comparison.
- `mycelium_architecture.json`: policy, hardware budgeting, S03, provenance and evolutionary persona.

Only install an engine after exact version pinning, license approval, dependency checks, and on isolated VM where appropriate. Don't replace the working NOX backend or forcefully restart trainer.

## Sources

- [vLLM serving](https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html)
- [OpenHands](https://github.com/OpenHands/OpenHands)
- [Browser Use](https://github.com/browser-use/browser-use)
- [TRL response-only SFT](https://huggingface.co/docs/trl/sft_trainer)
- [PEFT MoE LoRA](https://huggingface.co/docs/peft/en/package_reference/lora)
- [Unsloth MoE](https://unsloth.ai/docs/models/qwen3.5/fine-tune)


## ONEPASS + Google Drive task intake (source-only, 2026-11-12)

The existing `self_improvement.py` now exposes `propose_existing_nox_task_intake(...)`, backed by `nox_task_intake.py` and `nox_onepass_task_intake.json`. The task catalog contains 22 unique, provenance-linked tasks collected from Google Drive Genesis, November 10 gap audit, PATCH A/B, V16 and existing ONEPASS Notion receipt. It preserves historic A40/RTX Pro 6000 checkpoints as *claims requiring host verification*, not proven current training progress. It also explicitly records A40 OOM warnings from RunPod.

This integration is an intake **proposal inside the existing self-improvement module**, not another agent service or queue. Nothing is enqueued until existing task IDs, authenticated owner approval, STOP and ACL are checked by the live OneHost. No GPU job, auto restart, download, production merge, S03 write or schedule is triggered by import. Call `propose_existing_nox_task_intake(existing_task_ids, stop_available=verified_stop, owner_approved=authenticated_owner_approval)` to obtain candidate tasks, then the existing trusted queue must decide admission separately.

ONEPASS ZIP is referenced by exact historical name/SHA and 299 reported archive members, but it was not mounted or deployed by this PR. The live `NOX_ONEPASS.mjs` and `NOX_LIVE_ONEHOST_E2E.mjs` must be physically inspected and run on Windows before a full completion claim. This branch contains only source-level integration and tests; do not assert actual training or Windows acceptance.


## Release consolidation checkpoint — ONEPASS V2 + Vast archive, 12 November 2026

ONEPASS V2 is a newer already-created artifact than the original 299-member ONEPASS V1. Its complete ZIP SHA256 is `ef1cf8262483879e47eee75d1cd81fab22f1be4e3109a1ea7966f1cc04a6f127`, 302 files including 292 original WEB V25.1 files. Current-session local Node 22 tests **5/5 PASS** and `NOX_PREFLIGHT_ONLY=1` reports SOURCE/STATIC/PREFLIGHT PASS. Windows GPU, live OneHost, S03/STOP and weights acceptance remain HOLD. Do not claim deployment from local preflight.

Vast.ai snapshot for 2026-11-12 was reconstructed from two original private Drive parts; SHA256 `d5033064283f4127b52046f572e1f736f47eaf9276634b4739d8526347eb0e05` matched the stored checksum. Includes a 100,688,544-byte PEFT adapter, 50,345,312-byte knowledge GGUF, SQLite/FAISS and JSONL histories. `lora/state.json` reports `cycle=530`, `deployed_cycle=1`, `know_cursor=3488`, `sftq_offset=2329`, holdout ~0.8124; **these are snapshot-specific counters, not confirmed student optimizer global steps or full base weights**. The internal MANIFEST.sha256 names `models/bge-m3-Q4_K_M.gguf` which is absent from tar: full restore HOLD. Treat this as an immutable recovery source; do not overwrite current checkpoints, live weights, or production.

The 1–200 candidate catalog has downloaded upstream source snapshots on GitHub Actions; successful workflow jobs do NOT imply every indexed source fetched. Per-item `RESULTS.json` and recovery `RESULT.json` are authoritative; `OpenRouter Free` is a service rather than a source archive. Never install 200 engines as a group or run extra teachers on a busy A40.
