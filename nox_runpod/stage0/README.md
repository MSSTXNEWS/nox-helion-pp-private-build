# NOX HELION · RunPod Stage 0 Trainer
This is **real**, GPU-only QLoRA fine-tuning of a compatible Qwen3-8B foundation, not training an 8B model from random initialization or a claim of consciousness.

## Current state
Trainer source only; NOT launched and NOT integrated into NOX UI. Existing local NOX weights, S03 memory and GitHub CI are unchanged.

## Required
- RunPod NVIDIA GPU Pod with PyTorch/CUDA, enough VRAM/disk; no credentials committed.
- User-approved training set /workspace/nox/data/approved.jsonl, JSON Lines with {"text":"..."} per line. It must contain at least two real nonempty entries. Do not use chats or private data without approval.
- Install dependencies in the Pod: `python -m pip install -r requirements.txt`. Base image PyTorch should be CUDA compatible.
- Start: `python train_stage0.py --data /workspace/nox/data/approved.jsonl --out /workspace/nox/checkpoints/stage0 --max-steps 50 --save-steps 10`
- Checkpoints go to persistent /workspace/nox/checkpoints/stage0. Ensure /workspace is a persistent volume before creating any paid Pod.
- Ctrl+C / SIGTERM requests safe checkpoint after current step. Abrupt Pod deletion can still lose progress not yet saved.
- After training, output is **TRAINED_NOT_VALIDATED**. Evaluate RU/ES quality, regression and safety offline, then manually promote. Do NOT overwrite local NOX model or memory automatically.
- Stop/terminate the paid Pod after copying and verifying checkpoints. GitHub Actions integration, auto-stop, budget guard, downloading and validation still need implementation before unattended runs.
