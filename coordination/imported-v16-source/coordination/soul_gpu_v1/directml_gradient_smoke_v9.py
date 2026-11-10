"""NOX AMD DirectML bounded training preflight, not a QLoRA completion claim.

This tests that torch_directml can do one actual backpropagation step and
that parameter bytes changed. No user datasets, private data or code patches.
A DirectML PASS does not certify Qwen transformer PEFT/QLoRA compatibility.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime,timezone

def sha(tensor):
    return hashlib.sha256(tensor.detach().cpu().contiguous().numpy().tobytes()).hexdigest()

def run(root:Path):
    import torch
    import torch_directml
    device=torch_directml.device()
    # 32*32 tiny CPU-initialized parameter tensor, one bounded GPU step only.
    torch.manual_seed(7)
    weights=torch.nn.Parameter(torch.randn((32,32),dtype=torch.float32).to(device))
    optimizer=torch.optim.SGD([weights],lr=0.0001)
    inp=torch.full((32,32),0.01,dtype=torch.float32).to(device)
    before=sha(weights)
    optimizer.zero_grad(set_to_none=True)
    loss=((weights*inp).square()).mean()
    loss.backward()
    if weights.grad is None or not torch.isfinite(weights.grad).all().item():
        raise RuntimeError("DirectML gradient absent or nonfinite")
    optimizer.step()
    after=sha(weights)
    if after==before:
        raise RuntimeError("DirectML gradient step did not change weights")
    output={"schema":"NOX-DIRECTML-SMOKE-v1",
            "status":"GRADIENT_STEP_CHANGED_WEIGHTS",
            "timestamp":datetime.now(timezone.utc).isoformat(),
            "before_sha256":before,"after_sha256":after,
            "torch_version":torch.__version__,
            "device":"torch-directml",
            "batch_size":32,"parameter_count":1024,
            "qwen_qlora_verified":False,
            "gpu_temperature_verified":False,
            "training_adapters_created":0,
            "promoted_as_NOX_weights":False}
    dest=root/"brain"/"telemetry"/"directml_smoke.json"
    dest.parent.mkdir(parents=True,exist_ok=True)
    tmp=dest.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf-8")
    os.replace(tmp,dest)
    return output

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,required=True)
    a=p.parse_args()
    print(json.dumps(run(a.root),ensure_ascii=False,indent=2))
if __name__=="__main__":main()
