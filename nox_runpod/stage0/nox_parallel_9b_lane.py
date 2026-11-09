#!/usr/bin/env python3
"""NOX auxiliary 9B QLoRA lane on A5000.
Separate corpus/checkpoints from main lane. Never mutates donor/other adapter.
"""
import importlib.util,json,pathlib,sys,torch
R=pathlib.Path("/workspace/nox")
SOURCE=R/"tools/nox_prime_9b.py"
if not SOURCE.is_file():raise RuntimeError("Primary trainer source not ready")
if not torch.cuda.is_available():raise RuntimeError("CUDA GPU unavailable")
# Be conservative: primary learner takes priority; avoid exhausting 24GB.
mem=torch.cuda.mem_get_info()[0]
if mem < 9*1024**3:raise RuntimeError("NOX_PARALLEL_HOLD: less than 9GiB GPU free")
spec=importlib.util.spec_from_file_location("nox_secondary_lane",str(SOURCE))
m=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=m
spec.loader.exec_module(m)
m.WORK=R/"checkpoints/NOX_9B_PARALLEL_TECH"
m.CORPUS=R/"distillation/NOX_9B_PARALLEL_TECH.jsonl"
m.TOPICS=[
 "Advanced code generation and secure Python programming",
 "Distributed systems fault diagnosis and recovery",
 "CUDA performance profiling and memory optimization",
 "Mathematical reasoning and proofs",
 "Scientific experimentation and hypothesis testing",
 "Version control and software architecture",
 "Russian Spanish translation and cross-lingual learning",
 "Software testing and automated code improvement",
 "Knowledge provenance and retrieval augmented generation",
 "GPU efficient training and gradient methods",
 "Long-term autobiographical memory design",
 "SQL performance and consistency"]
m.verify()
tok,model=m.load_4bit()
m.create_corpus(tok,model,4)
del model
torch.cuda.empty_cache()
tok,model=m.load_4bit()
m.train(tok,model,1,384,4,16,batch_size=1)
print(json.dumps({"status":"SECONDARY_NOX_9B_ADAPTER_SAVED_UNMERGED",
"location":str(m.WORK),
"note":"Parallel LoRA branch is not incorporated in the unified NOX model until compatibility and quality checks."}),flush=True)
