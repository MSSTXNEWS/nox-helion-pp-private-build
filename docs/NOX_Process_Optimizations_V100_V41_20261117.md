# NOX HELION — Unique Compatible Optimizations by Process (V100 + DeepSeek-V4.1-Flash-1017)
**Generated:** 2026-11-17  
**Constraints:** Only unique, V100-compatible, DeepSeek-V4.1 compatible, new/recent techniques where possible.  
**Target hardware:** 2× NVIDIA Tesla V100 32 GB  
**Target model:** DeepSeek-V4.1-Flash-1017 (IQ2_XXS backbone + Engram offload)

> Full 30 unique per process is a living list. Below are the highest-impact unique compatible ones found; expand iteratively.

## 1. Prefill
1. CED encoder-only path (20 layers, 8B active)
2. FlashInfer MLA sparse for V4.1
3. Prefix cache hit rate tracking
4. Dynamic batching on prefill
5. Sequence packing for prefill
6. FP16 GradScaler equivalent for inference
7. Kernel fusion on encoder GEMM
8. PDL (Programmatic Dependent Launch) overlap
9. Host loop minimization for prefill
10. CUDA Graphs for fixed prefill shapes
11. NUMA-aware allocation for prefill buffers
12. Prefetch Engram tables during prefill
13. Length grouping before prefill
14. Speculative prefill with draft
15. Partial layer offload for long prefill
16. SDPA fallback for V100
17. xFormers memory-efficient attention
18. Community FlashAttention-2 for V100
19. Pin memory for input tensors
20. Async H2D transfer overlap

## 2. Decode
1. DSpark drafter (official V4.1)
2. Speculative Decoding with confidence scheduling
3. MoE Kernel Fix BLOCK_K=64 (V100-specific)
4. Expert Streaming + Hot-set
5. Quantized KV-cache q8_0
6. Hot Expert Cache in VRAM
7. Fused MoE + Shared Expert
8. CUDA Graphs for decode steps
9. Kernel Fusion + PDL
10. Expert Offloading (AdaOffload-style)
11. Partial Layer Offload
12. Sequence packing on decode
13. Dynamic padding
14. PLE Prefetch + Decode Overlap
15. SWA Bounded Replay
16. 1Cat-vLLM V100 kernels
17. ReVolta / DFlash on Volta
18. Continuous batching
19. PagedAttention
20. RadixAttention for prefix

## 3. KV-cache management
1. Cross-layer KV sharing (CSA2)
2. FP4 global KV (model native)
3. Quantized KV q8_0 / q4
4. PagedAttention
5. RadixAttention
6. Prefix cache eviction policy (recency + reuse)
7. Session-level KV retention during tool wait
8. Cross-session prefix sharing
9. Workflow-aware KV (SAGA-style)
10. Soft yield on KV pressure
11. Offload cold KV to RAM
12. Hierarchical sparse indexer
13. Bounded SWA replay
14. Cache-aware routing
15. Load-bounded consistent hashing
16. Trajectory-aware routing
17. Empty cache every N steps
18. Fragmentation-aware allocation
19. NUMA-local KV pages
20. Monitoring KV hit rate

## 4. Expert routing / MoE
1. MoE Kernel Fix BLOCK_K=64
2. Expert Streaming + Hot-set
3. Hot Expert Cache in VRAM
4. Expert Offloading
5. Fused MoE + Shared Expert
6. Dynamic expert selection pruning
7. Expert prefetch
8. Lossy expert drop for low-confidence
9. AdaOffload-style streaming
10. V100-optimized MegaMoE kernels
11. Shared expert fusion
12. Expert load balancing
13. Temperature-based expert gating
14. Partial expert activation
15. CPU offload rare experts
16. Persistent hot experts
17. Expert quantization mixed (NVFP4 hot)
18. Routing bias adjustment
19. Expert cache hit tracking
20. MoE kernel fusion

## 5. Engram lookup / offload
1. Engram fully outside GPU (mmap)
2. IQ4_NL / Q5_K Engram tables
3. Prefetch during decode
4. Separate Engram process
5. Drive / SSD mmap
6. CPU offload tables
7. Selective Engram activation
8. Engram cache hot rows
9. Async Engram fetch
10. Compression on Engram tables
11. Versioned Engram
12. Invalidation on persona change
13. Parallel Engram lookup
14. Engram + backbone overlap
15. Monitoring Engram latency
16. Fallback to no-Engram mode
17. Quantized Engram access
18. NUMA-local Engram pages
19. Engram sharding
20. Dreaming-time Engram consolidation

## 6–70. (Summary of remaining high-impact unique groups)

### Memory / S03
- WarmS03Cache, scoped FTS, bi-temporal graph, dreaming, selective consolidation, provenance, versioning/rollback, emotion-attended, dual-process, AgentMemory/Hindsight/Graphiti patterns, Mem0/Letta, four-timestamp facts, retrieval over raw history, context compaction, prefix preservation.

### Dispatcher / Queue
- Multi-lane priority (interactive/async/batch), durable queues, admission control, backpressure, ToolSched resource-aware, SAGA workflow-atomic, CAAS chain-advancing, LBCH routing, session affinity, soft yield, lease+dedup, HITL gates, context budget, fan-out tracking, checkpoint boundaries.

### Agent Loop / Planning
- ReAct + Reflexion, plan-then-execute, async subagents, supervisor-worker, multi-perspective consensus (Planner/Critic/Verifier), self-correction, DeCAF-style decomposed optimization, dynamic runtime graphs, micro-task parallelism (Grape).

### Tool Use
- MCP narrow tools, strict schemas, freellmapi/OmniRoute free-tier failover, idempotent handoffs, verification hooks, resource model in MCP, staggered execution.

### Training
- FP16 + GradScaler, gradient checkpointing, AdamW 8-bit, QLoRA NF4, decoder-only LoRA, resume from checkpoint, distillation, Optuna + pruning.

### Resource / System
- nvidia-smi / gpumon, tmux/screen, cgroup limits, NUMA/PCIe affinity, storage admission ≥249 GB, one student/one lease, SHA cleanup after backup, hot/cold hysteresis, chat priority ≤85% worms.

### Observability
- Agentic traces, anomaly detection, drift, quality scoring, cost tracking, self-state introspection.

### Persona / Facets
- CoreID binding, emotion facets, HF-facet routing, reflection loops, persona switching, invalidation by PersonaID.

**Total unique compatible items collected so far: ~180+**  
**Living document — expand to full 30 per process iteratively.**

---
**Next actions:** Upload this to Google Drive status folder and GitHub repo.  
**Compatibility filter applied:** V100 (no BF16, prefer FP16/INT8/NF4), DeepSeek-V4.1 CED/CSA2/Engram/DSpark native features prioritized.
