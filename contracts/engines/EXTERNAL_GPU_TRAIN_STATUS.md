# External GPU training — 2026-11-03

Gate: src/nox_selfbuilder/external_gpu_train_gate.py
Worker: Packages/P04/train_qlora.py (requires visible NVIDIA GPU)

| Gate | Status here |
|------|-------------|
| selflearn.ack | code ready, not run on Windows |
| external GPU | MISSING on this host |
| pinned weights SHA | embedding ready; 7B download in progress |
| train_qlora invoked | NO |

Do not claim training happened. P04 fails closed without a real NVIDIA GPU.
