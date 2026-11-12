#!/usr/bin/env python3
"""NOX V28 Speed Lab: recommend safe profile-driven A/B experiments.

NO CODE EXECUTION, runtime reload or GPU change. Do not assume internet
benchmarks are transferable to Qwen3.5-9B, RX6650M, A40, or current NOX.
"""
from __future__ import annotations
import math
SCHEMA="nox-speed-lab-v28"
TRIALS={
  "PREFIX_CACHE_AB":{
    "tier":"INFERENCE","metric":"p95_ttft_ms","direction":"lower","regression_guard":"RAG_CITATION_AND_PRIVACY",
    "why":"Repeated trusted system/skill prefixes could be reused without model switching.",
  },
  "CHUNKED_PREFILL_AB":{
    "tier":"INFERENCE","metric":"p95_ttft_ms","direction":"lower","regression_guard":"LONG_CONTEXT_ACCURACY",
    "why":"Chunk long prompts without starving live decode under a supported backend.",
  },
  "SPECULATIVE_DECODE_AB":{
    "tier":"INFERENCE","metric":"p95_intertoken_ms","direction":"lower","regression_guard":"SAME_TOKEN_OUTPUT_AND_MEMORY",
    "why":"Verifier + compatible lightweight draft may reduce decode latency if resources fit.",
  },
  "KV_CACHE_QUANT_AB":{
    "tier":"INFERENCE","metric":"peak_vram_mb","direction":"lower","regression_guard":"LONGMEMORY_QUALITY",
    "why":"Only supported precision and architecture; do not corrupt Gated DeltaNet or vision context.",
  },
  "TRAIN_LENGTH_PACK_AB":{
    "tier":"TRAINING","metric":"tokens_per_second","direction":"higher","regression_guard":"SOURCE_SEPARATED_HOLDOUT",
    "why":"Length buckets reduce padding and shape recompiles while respecting loss masks.",
  },
  "TRAIN_FUSED_KERNEL_AB":{
    "tier":"TRAINING","metric":"tokens_per_second","direction":"higher","regression_guard":"NUMERICAL_GRADIENT_PARITY",
    "why":"Test Liger/fused CE/causal-conv1d only for exact installed Qwen architecture/kernel/driver.",
  },
  "DATA_PREFETCH_AB":{
    "tier":"TRAINING","metric":"gpu_compute_idle_fraction","direction":"lower","regression_guard":"CHECKPOINT_RESTART_PARITY",
    "why":"Move approved JSONL loading and preparation onto CPU while keeping GPU chat priority.",
  },
}
def _metric(signal,key):
    value=signal.get(key)
    return value if type(value) in (int,float) and math.isfinite(value) and value>=0 else None

def propose_speed_trials(signals:dict,policy:dict)->dict:
    if not isinstance(policy,dict) or policy.get("signed_by_native_owner") is not True:
        return {"schema":SCHEMA,"state":"HOLD_NATIVE_POLICY","experiments":[]}
    if policy.get("stop_requested") is not False:
        return {"schema":SCHEMA,"state":"HOLD_STOP","experiments":[]}
    if not isinstance(signals,dict) or signals.get("measured") is not True:
        return {"schema":SCHEMA,"state":"HOLD_NO_LIVE_PROFILE","experiments":[]}
    if (signals.get("sensor_valid") is not True or
        signals.get("machine_signature_verified") is not True or
        signals.get("source_model_sha256_verified") is not True):
        return {"schema":SCHEMA,"state":"HOLD_HARDWARE_SOURCE_PROOF","experiments":[]}
    candidates=[]
    def add(code,reason):
        entry=TRIALS[code]
        candidates.append({"code":code,"tier":entry["tier"],
                           "metric":entry["metric"],"direction":entry["direction"],
                           "regression_guard":entry["regression_guard"],"reason":reason,
                           "owner_benchmark_replay_required":True,
                           "auto_apply":False})
    backend=signals.get("backend_capabilities")
    if not isinstance(backend,dict):
        backend={}
    ttft=_metric(signals,"p95_ttft_ms")
    token=_metric(signals,"p95_intertoken_ms")
    context=_metric(signals,"prompt_tokens_p95")
    vram=_metric(signals,"vram_utilization_pct")
    repeated=_metric(signals,"repeated_prefix_rate")
    if repeated is not None and repeated>=0.20 and backend.get("prefix_cache") is True:
        add("PREFIX_CACHE_AB","Repeated context prefixes measured in owner trace.")
    if ttft is not None and ttft>=1800 and context is not None and context>=2048 and backend.get("chunked_prefill") is True:
        add("CHUNKED_PREFILL_AB","High first-token latency on observed long prompts.")
    if (token is not None and token>=100 and backend.get("speculative") is True
            and signals.get("draft_model_sha_verified") is True and
            signals.get("draft_tokenizer_compatible") is True
            and _metric(signals,"free_vram_mb") is not None
            and signals["free_vram_mb"]>=signals.get("draft_required_mb",10**12)):
        add("SPECULATIVE_DECODE_AB","Only an independently verified compatible draft is eligible.")
    if vram is not None and vram>=85 and backend.get("kv_quant") is True:
        add("KV_CACHE_QUANT_AB","VRAM pressure measured; independent long-context retention test required.")
    if signals.get("training_job_active") is True and signals.get("chat_busy") is not True:
        if (_metric(signals,"train_length_variance") or 0)>0.35 and backend.get("length_pack") is True:
            add("TRAIN_LENGTH_PACK_AB","Length dispersion measured and loss-mask parity requires testing.")
        if backend.get("fused_kernel_installed") is True and signals.get("kernel_architecture_verified") is True:
            add("TRAIN_FUSED_KERNEL_AB","Installed kernels on exact device are eligible for gradient parity A/B.")
        if (_metric(signals,"gpu_compute_idle_fraction") or 0)>=0.18 and backend.get("async_prefetch") is True:
            add("DATA_PREFETCH_AB","Measured dataloader wait, not fabricated GPU utilization.")
    priority={"PREFIX_CACHE_AB":0,"CHUNKED_PREFILL_AB":1,"DATA_PREFETCH_AB":2,
              "TRAIN_LENGTH_PACK_AB":3,"TRAIN_FUSED_KERNEL_AB":4,
              "SPECULATIVE_DECODE_AB":5,"KV_CACHE_QUANT_AB":6}
    candidates.sort(key=lambda x:priority[x["code"]])
    # One controlled A/B at a time; never change three knobs and claim causality.
    return {"schema":SCHEMA,
            "state":"TRIALS_RECOMMENDED_NOT_APPLIED" if candidates else "NO_MEASURED_SPEED_OPPORTUNITY",
            "experiments":candidates[:3],"max_concurrent_ab_trials":1,
            "active_gpu_jobs_started":0,"production_mutations":False,
            "no_claimed_speedup_without_same_workload_ab":True}
