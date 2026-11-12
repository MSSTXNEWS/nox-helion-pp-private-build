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
