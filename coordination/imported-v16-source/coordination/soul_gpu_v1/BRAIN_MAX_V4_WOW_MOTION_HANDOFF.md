# NOX BRAIN MAX V4 · UI progress + training handoff
instructions_version: 0.0.6
Date: 2026-11-06

User request: the ONE local PowerShell controller must open the existing WPF/WebView2 NOX.HELION.exe during training, preserve 70GB intelligence / 70GB memory / 70GB skills + 60GB free reserve, use sequential Qwen model sizes, avoid Downloads and duplicate pulls, train LoRA with real counters, and preserve prior weights/memory.

Verified source in PR #162:
- ui/menu-pages/nox-holo-motion-v7.mjs; ui/menu-pages/nox-holo-runtime-v7.mjs
- ui/nox-holo-motion-v7.css; ui/nox-holo-motion-v7.mjs
- coordination/soul_gpu_v1/train_qlora.py; synaptic_memory_v1.py; NOX GPU source modules.

Current portable local bundle is user-delivered separately:
- NOX_BRAIN_MASTER_V4.ps1: checks quotas, reuses Ollama tags, ordered downloads, opens REAL installed NOX.HELION.exe, calls trainer, writes real JSON status and console progress
- nox_train_with_status.py: CUDA QLoRA on approved source-disjoint data; per-step telemetry, rollback/pending evidence, SHA256 manifests
- README_RU.txt

The local controller was tested for Python syntax and dataset source-isolation only. Not tested on user's Windows GPU. No EXE build, WebView2 V7 physical gate, training complete, or direct S03 integration should be claimed.
No Downloads operations, no duplicate model pull, no deletion. V7 assets in repository do not automatically imply the installed EXE displays V7. UI integration remains HOLD until exact local HTML/WPF owner contract and direct physical check.

Do not create a second EXE or dummy UI. Existing native NOX is the only UI destination.
Do not mark completion based on staged code or logs; require witnessed installed-EXE and trainer evidence.
