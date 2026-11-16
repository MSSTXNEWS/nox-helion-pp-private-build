# DeepSeek teacher → Llama student: source-only candidate

**State: SOURCE CANDIDATE ONLY / training disabled.** This pack does not download model files, access OneHost, write to S03, launch a GPU job, or alter checkpoints.

## Compatibility decision

Use the IQ2_XXS GGUF only for inference and generation of teacher answers. Do not optimize or attach an adapter to those quantized GGUF shards. The existing repository recipe accepts an immutable Hugging Face base revision, architecture, config/tokenizer hashes, safetensors weight manifest, and bounded three-way corpus; it explicitly rejects GGUF and supports FP16 only for the V100/SM70 path.

Candidate student: `deepseek-ai/DeepSeek-R1-Distill-Llama-8B`, pinned to `6a6f4aa4197940add57724a7707d069478df56b1`. Hugging Face's API reports it is ungated, `LlamaForCausalLM`, with two safetensors totaling 16,060,556,354 bytes. This is compatible at the source-format/module level with the existing adapter recipe's Llama projection module names. Actual load, installed trainer support, GPU memory fit, and useful quality are still unverified.

Use response-level distillation: store teacher-produced responses with prompt/output hashes and exact teacher/model/code provenance, then perform response-only SFT/LoRA on the student. This is not logits-based distillation. The manifest leaves the corpus and native resource gates unresolved, so training cannot begin.

## License

DeepSeek-V4.1-Flash-1017 / the pinned ISTA-DASLab IQ2_XXS quantization is listed as MIT. The student repository contains an MIT LICENSE file and an MIT metadata tag, but its official README says the Llama-8B student is derived from Llama 3.1 and originally licensed under the Llama 3.1 license. This pack treats the student lineage/license question as unresolved and blocks training release until reviewed; do not redistribute a trained artifact before that review.

## Required before any training

- Fresh authorized OneHost STOP, writer lease, process, GPU, RAM, SSD, and storage readback.
- Exact local SHA-256 readback of required teacher files and student HF files; the manifest hashes are upstream expectations, not proof of local installation.
- Pinned config and tokenizer runtime SHA-256 values plus successful architecture and one-batch memory preflight.
- Rights-reviewed, owner-approved train/dev/frozen-holdout corpus with independent source groups, per-row provenance, exact overlap checks, and hashes.
- A single admitted trainer owner only. Never use old Qwen jobs or their optimizer lineage for this student.
- Atomic checkpoints with trainer, optimizer, scheduler, FP16 scaler, RNG, adapter, model/tokenizer/corpus and source identity; a separate restore must pass before continuation.
- Baseline and post-training RU/ES evaluation on the same frozen holdout, plus quality review and measured memory/latency. No promotion without an accepted improvement.

The source tests validate this manifest and its fail-closed state only. They do not run inference, training, native preflight, or license interpretation.
