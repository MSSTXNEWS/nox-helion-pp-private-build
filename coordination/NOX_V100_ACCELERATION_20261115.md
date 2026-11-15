# NOX PRIME — V100 accelerator and recovery registry
Version: 2026-11-15 / instructions_version 0.0.6
Status: SOURCE-INTEGRATED CANDIDATES, NOT LIVE INSTALLED. Do not create second backend/scheduler.

## Original native server (verified, preserve)
Instance Vast.ai 60509551, 2 Tesla V100-SXM2 32 GB (Volta SM70). Native evidence: https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43721692544
Driver 580.178.04, CUDA runtime 12.4, torch 2.6.0+cu124 (sm_70 compiled), cuDNN 9.1, DeepSpeed 0.20.0, Transformers 5.23.0, Accelerate 1.15.0, Datasets 5.2.0, Safetensors 0.8.0, Triton 3.2.0, Python 3.12.16 in /opt/venv. No blind reinstall. Last verified SSD free ~16.47 GB; GPU1 busy/ownership unknown and independent full optimizer restore unverified. No forced restart/delete.

## Components: source state, upstream, physical admission
1. P0 STOP GPU0/GPU1, crash recovery, 80-85% steady useful work and 95% peak soft backpressure: existing nox_runpod/teacher_mesh/v43/nox/resource_brain.py. Callback policies source-tested; native STOP latch, full-state save/restore, owner lease and readback not yet wired on host. No hardware utilization hard cap.
2. P0 existing supervisor: inspect real OneHost service first; only the original service gets on-failure recovery with bounded StartLimitBurst/backoff. Manual STOP blocks auto-resume. https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html
3. P0 full optimizer recovery: existing V135 trainer plus verified_resume.py requires owner-signed exact checkpoint-N, full model/optimizer sharded states, original DeepSpeed config and full tree SHA, offsite restore before Trainer resume_from_checkpoint. Do not start new GPU1 workload without lease. https://huggingface.co/docs/transformers/trainer_recipes
4. P0 DeepSpeed ZeRO-3 optimizer CPU offload: ALREADY INSTALLED. Only tune measured parameters while preserving S03 and the original student. https://huggingface.co/docs/transformers/main/deepspeed
5. P0 resource telemetry: existing NVML/nvidia-smi/Resource Brain sufficient for basic gauges. Optional DCGM exporter requires host compatibility and no second nv-hostengine. https://docs.nvidia.com/datacenter/cloud-native/gpu-telemetry/latest/dcgm-exporter.html
6. P1 llama.cpp native inference: compare existing binary with official llama.cpp; only if current engine supports it, trial continuous batching, right-sized slots, cache_prompt and owner-scoped KV cache, context budgeting, thread count. Avoid new inference server. https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md
7. P1 compiled CUDA Volta backend: possible isolated CUDA12 source build with CMAKE_CUDA_ARCHITECTURES=70; benchmark cuBLAS vs GGML_CUDA_FORCE_MMQ. The latter may reduce VRAM but worsen large-batch throughput; no unconditional enable. https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md
8. P1 model-free n-gram speculative decoding: llama.cpp ngram-simple or ngram-mod only if current installed engine supports options; benchmark output correctness and token/s, may be slower. https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md
9. P1 cognitive search: original S03 SQLite with FTS5/BM25 lexical fast path, no duplicate DB. Optional sqlite-vec embeddings on same scoped store if ABI and owner ACL verified. https://www.sqlite.org/fts5.html ; https://github.com/asg017/sqlite-vec
10. P1 bounded rerank: optional SentenceTransformers CrossEncoder rerank top-k after S03/RAG; prefer CPU-first to keep GPU0 chat latency low; verify quality against baseline. https://sbert.net/docs/cross_encoder/usage/usage.html
11. P1 optional ONNX Runtime encoder (isolated environment only): CUDA 12.4/cuDNN9 needs compatible ORT 1.20.x CUDA12 package; newer ORT releases require CUDA12.8/13. DO NOT blanket pip upgrade on original 2.6+cu124 environment. https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html
12. P2 recovery telemetry: native global_step/optimizer, loss, checkpoint SHA, external restore receipt, TTFT p50/p95, true decode token/s (NOT SSE fragments), STOP and crash reasons; preserve single canonical journal.

## Incompatible or disallowed
CUDA 13 toolchain removed Volta offline compilation: https://docs.nvidia.com/cuda/cuda-features-archive/
FlashAttention-2/3 current CUDA implementation supports Ampere/Ada/Hopper, not V100: https://github.com/Dao-AILab/flash-attention
No unsupported BF16/FP8, second model/chat/backend/scheduler, GPUs treated as pooled 64 GB, uncontrolled overclock, force-kill unknown PID, disk wipe or LoRA/PEFT.

## Native execution checklist (all required for real PASS)
- Owner v1 GET https://console.vast.ai/api/v1/instances/?owner=me exactly matches running 60509551; SSH host Ed25519 pinned. V51 GitHub workflow is owner manual opt-in and READ-ONLY only, not blanket native write authorization.
- Identify running OneHost service and original GPU0/1 PIDs; original manual STOP, S03 SQLite fsync, GPU1 optimizer global_step and genuine owner lease.
- Verify SHA and INDEPENDENT restoration of S03/full optimizer offsite; ensure free SSD/cgroup/VRAM for one checkpoint, preserve current chat model on GPU0.
- Stage approved packages in reversible isolated env, one controlled change, real same-prompt TTFT/throughput and S03 owner quality, then rollback or promote based on evidence.
- Manual STOP latches until RESUME; after unexpected failure restart only original owned process, at most 3 attempts with >=60s backoff, after checkpoint/S03 readback.
- Remove only verified obsolete duplicates with trusted backup and actual freed-space readback. Record production PASS only from native server.

This registry does not assert that optional components have been downloaded, installed or enabled. Current server already contains the core GPU training stack; P0 missing pieces are host write binding, offsite recovery and process ownership, not another library catalog.
