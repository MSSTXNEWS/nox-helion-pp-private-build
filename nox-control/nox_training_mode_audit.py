#!/usr/bin/env python3
"""Read-only audit of NOX training mode. Does NOT delete, stop, or alter anything."""
import json, os, re, datetime as dt
from pathlib import Path
ROOT = Path("/workspace/nox")
WEIGHT_SUFFIXES={".safetensors",".bin",".pt",".pth"}
CODE_SUFFIXES={".py",".sh"}
def proc_list():
    out=[]
    for p in Path("/proc").iterdir():
        if not p.name.isdigit(): continue
        try:
            cmd=(p/"cmdline").read_bytes().replace(b"\x00",b" ").decode("utf-8","replace")
        except (OSError,UnicodeError): continue
        if not any(w in cmd.lower() for w in ("distill","train","supervis","torchrun","accelerate")): continue
        if "nox_training_mode_audit.py" in cmd: continue
        out.append({"pid":int(p.name),"cmd":cmd[:600]})
    return out[:60]
def audit():
    result={"checked_at":dt.datetime.now(dt.timezone.utc).isoformat(),"root":str(ROOT),
            "processes":proc_list(),"lora_files":[],"full_weight_candidates":[],"code_evidence":[]}
    ignore={".git","site-packages","node_modules","venv","prime9b-venv","cache","dataset","datasets","THREE_TEACHERS"}
    for base, dirs, names in os.walk(ROOT):
        relative=Path(base).relative_to(ROOT)
        depth=len(relative.parts)
        dirs[:]=[d for d in dirs if d not in ignore and not d.startswith(".") and depth<9]
        for name in names:
            f=Path(base)/name
            suffix=f.suffix.lower()
            if suffix not in WEIGHT_SUFFIXES|CODE_SUFFIXES: continue
            try: size=f.stat().st_size
            except OSError: continue
            path=str(f.relative_to(ROOT))
            lower=path.lower()
            if suffix in WEIGHT_SUFFIXES:
                record={"path":path,"bytes":size}
                if "adapter" in lower or "lora" in lower:
                    result["lora_files"].append(record)
                elif size>=500_000_000:
                    result["full_weight_candidates"].append(record)
            elif suffix in CODE_SUFFIXES and (any(t in lower for t in ("distill","trainer","training","supervis","prime"))):
                try:
                    content=f.read_text(encoding="utf-8",errors="replace")[:250000]
                except OSError: continue
                matched=[]
                for label,pattern in {
                    "adapter_training":r"(?i)\b(LoraConfig|get_peft_model|PeftModel|prepare_model_for_kbit_training)\b",
                    "adapter_saving":r"(?i)(adapter_model|save_pretrained\s*\()",
                    "optimizer_update":r"(?i)(optimizer\.step\s*\(|scaler\.step\s*\(|trainer\.train\s*\()",
                    "full_finetune_indicator":r"(?i)(full_finetun|full_fine_tun|train_all_parameters|requires_grad_\s*\(\s*True\s*\))"
                }.items():
                    if re.search(pattern, content): matched.append(label)
                if matched: result["code_evidence"].append({"path":path,"signals":matched})
    for key in ("lora_files","full_weight_candidates","code_evidence"):
        result[key]=sorted(result[key],key=lambda item:item["path"])[:100]
    result["conclusion"]="UNVERIFIED"
    result["why"]="File presence and code keywords cannot prove completed full-weight training or compatible checkpoints; review actual trainer configuration and checkpoint loading."
    result["safe_to_delete_adapters"]=False
    result["mutations"]=0
    return result
print("NOX_MODE_AUDIT "+json.dumps(audit(),ensure_ascii=False))
