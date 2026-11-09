# NOX PRIME · RunPod stage 0 (Qwen3.5-9B)

## State: source committed, not executed. No GPU rented here.
Actual Windows model: `C:\NOX_HELION\NOX_NEW\brain\prime\models\NOX_PRIME_9B_INHERITED` with config `model_type=qwen3_5`, four safetensors shards (17.98 GiB observed). Windows contents are NOT accessible from the cloud or ChatGPT. Never silently substitute a standard Qwen checkpoint for the user's unique local model.

## Before billing a GPU
1. Have an actual user-approved JSONL dataset, with at least 2 rows of `{"text":"..."}`. No fabricated records, no sensitive memory/chats without explicit approval.
2. Transfer the verified original model directory to a persistent RunPod folder (for example `/workspace/nox/models/NOX_PRIME_9B_INHERITED`) using SSH/SFTP or an owner-controlled encrypted upload. Verify ALL four safetensors shards, `config.json`, tokenizer files, and SHA-256 hashes against Windows. Do not place model files in GitHub.
3. Implement and verify a Pod autostop/termination guard BEFORE paid unattended run; storage also costs money. Verify CUDA/kernel compatibility and 24 GiB VRAM constraints first. A 48 GiB GPU may be needed if 4090 OOMs.
4. Install a tested CUDA/PyTorch build and dependencies; validate exact package compatibility on the real GPU. `requirements.txt` gives ranges, not a proven lockfile.

## Manual command, only AFTER preflight
`python train_stage0.py --model /workspace/nox/models/NOX_PRIME_9B_INHERITED --data /workspace/nox/data/approved.jsonl --out /workspace/nox/checkpoints/stage0 --max-steps 10 --save-steps 5`

This performs **QLoRA adaptation**, not teacher distillation or absorption of an arbitrary second model. A separate teacher-generation/selection/scoring workflow is required for distillation. Result is TRAINED_NOT_VALIDATED; do not auto-promote into Windows NOX. Stop the Pod explicitly and verify checkpoints were retained and transferred. Do not delete old working model or S03.
