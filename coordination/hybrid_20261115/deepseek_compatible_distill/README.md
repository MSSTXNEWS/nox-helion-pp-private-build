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

## RU/ES fixed-holdout scorer

`score_ru_es_holdout.py` is a source-only scorer for independent, rubric-scored outputs. It reads a frozen JSONL case index (`case_id`, `language`, `prompt_sha256`, `refusal_expected`, `safety_sensitive`) and paired baseline/candidate score receipts. Receipts bind the same case IDs and prompt hashes to exact model and evaluator SHA-256 values, with answer hash, language-match, refusal decision, safety pass, 0–1 quality score, and 0–1 evaluator confidence. Raw prompt and answer text are not part of the repository or score report.

The scorer verifies the exact case-file SHA, rejects duplicate, missing, extra, or mismatched cases, requires RU and ES plus both expected refusal outcomes and a safety-sensitive case in each language, and reports per-language rates, confidence means, paired composite deltas, deterministic stratified bootstrap 95% intervals, and an equal-weight RU/ES aggregate. Safety, refusal, and language regressions prevent the numeric gate from clearing. The report is `SCORED_NUMERIC_ONLY`; it never authorizes promotion or starts training. Human quality review, manifest admission, restore, license, corpus, and native STOP/resource gates still apply.

Example invocation after a reviewed holdout and score receipts exist:

```sh
python score_ru_es_holdout.py \
  --cases holdout-cases.jsonl \
  --baseline baseline-scores.jsonl \
  --candidate candidate-scores.jsonl \
  --expected-dataset-sha256 <holdout-sha256> \
  --baseline-model-sha256 <baseline-sha256> \
  --candidate-model-sha256 <candidate-sha256> \
  --evaluator-sha256 <evaluator-sha256> \
  --minimum-improvement-threshold 0.01 \
  --output paired-report.json
```


## Staged session example

One user-requested session correction is recorded in the manifest as `STAGED` with prompt, completion, provenance context, SHA-256 hashes, and `train_candidate` assignment. It is excluded from dev/holdout and is not an admitted training corpus row. Since the frozen holdout membership is not yet populated, the verifier reports `STAGED_PAIR_HOLDOUT_NOT_VERIFIABLE`; the pair is not cleared for training. Tests cover hash tampering, holdout collision, sensitive-pattern detection, and STOP preservation. No quality improvement or training run is claimed.

