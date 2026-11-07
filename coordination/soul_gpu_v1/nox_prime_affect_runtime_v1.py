"""Load ACTUALLY TRAINED NOX SOUL Stage-1 weights for evidence-limited inference.

Only English text classification is evaluated. This model does not represent
subjective feelings, RU/ES competence, S03 memory, or a modified main LLM.
The trained .safetensors file must match the accepted CURRENT_VERIFIED receipt.
No network, no training, no writes, CPU inference only.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import threading

_CACHE={}
_LOCK=threading.Lock()
_SHA=re.compile(r"^[0-9a-f]{64}$")
_CYRILLIC=re.compile(r"[\u0400-\u052f]")
_SPANISH_CHARS=re.compile(r"[¿¡ñáéíóúü]",re.I)

def _sha256(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for data in iter(lambda:f.read(1048576),b""):
            h.update(data)
    return h.hexdigest()

def _resolve_accepted(root):
    base=(Path(root).resolve()/"brain"/"intelligence"/"soul_stage1").resolve()
    receipt=base/"CURRENT_VERIFIED.json"
    if not receipt.is_file() or receipt.is_symlink():
        return None
    obj=json.loads(receipt.read_text(encoding="utf-8"))
    source=obj.get("model_path")
    sha=obj.get("model_sha256")
    if not isinstance(source,str) or not isinstance(sha,str) or not _SHA.fullmatch(sha):
        raise ValueError("AFFECT_INVALID_RECEIPT")
    weights=Path(source).resolve()
    if base not in weights.parents or weights.name!="best.safetensors":
        raise PermissionError("AFFECT_WEIGHTS_OUTSIDE_NOX")
    if not weights.is_file() or weights.is_symlink():
        raise FileNotFoundError("AFFECT_WEIGHTS_MISSING")
    evidence=weights.parent/"TRAINING_EVIDENCE.json"
    if not evidence.is_file() or evidence.is_symlink():
        raise FileNotFoundError("AFFECT_EVIDENCE_MISSING")
    audit=json.loads(evidence.read_text(encoding="utf-8"))
    if audit.get("status")!="HOLDOUT_PASSED" or audit.get("weights_sha256")!=sha:
        raise ValueError("AFFECT_NOT_HOLDOUT_ACCEPTED")
    if not isinstance(audit.get("decision_threshold"),(int,float)) or not 0<audit["decision_threshold"]<=1:
        raise ValueError("AFFECT_BAD_THRESHOLD")
    if abs(float(audit["test_micro_f1"])-float(obj.get("test_micro_f1",-1)))>0.00002:
        raise ValueError("AFFECT_EVALUATION_RECEIPT_MISMATCH")
    actual=_sha256(weights)
    if actual!=sha:raise ValueError("AFFECT_WEIGHT_HASH_MISMATCH")
    return {"path":weights,"sha256":sha,"threshold":float(audit["decision_threshold"]),
            "test_micro_f1":float(audit["test_micro_f1"]),
            "classes":audit.get("classes")}

def status(root):
    """No heavy import. Receipts are checked on status, not on every chat turn."""
    try:
        accepted=_resolve_accepted(root)
        if not accepted:
            return {"available":False,"scope":"EN_ONLY","reason":"NO_ACCEPTED_WEIGHTS"}
        return {"available":True,"scope":"EN_ONLY","model_sha256":accepted["sha256"],
                "holdout_micro_f1":accepted["test_micro_f1"],
                "class_labels":accepted["classes"],"connected_to_main_llm":False}
    except (OSError,ValueError,TypeError,PermissionError,KeyError) as exc:
        return {"available":False,"scope":"EN_ONLY","reason":type(exc).__name__}

def _model(root):
    import torch
    from safetensors.torch import load_file
    from nox_prime_soul_stage1_train import _net, GROUPS
    accepted=_resolve_accepted(root)
    if accepted is None:return None,None,None
    if accepted["classes"]!=list(GROUPS):
        raise ValueError("AFFECT_LABEL_ORDER_MISMATCH")
    key=(str(accepted["path"]),accepted["sha256"])
    with _LOCK:
        if key not in _CACHE:
            weights=load_file(str(accepted["path"]),device="cpu")
            net=_net()
            net.load_state_dict(weights,strict=True)
            net.eval()
            _CACHE.clear()
            _CACHE[key]=net
        return _CACHE[key],accepted,torch

def assess(root,text):
    """Return measured six-label signal, NOT a factual statement of emotion.

    Russian/Spanish are not covered by this training; fail closed rather than
    claiming multilingual accuracy from English-only GoEmotions.
    """
    if not isinstance(text,str) or len(text.strip())<8 or len(text)>2000:
        return {"available":False,"reason":"TOO_SHORT_OR_LONG","scope":"EN_ONLY"}
    if _CYRILLIC.search(text) or _SPANISH_CHARS.search(text):
        return {"available":False,"reason":"NON_EN_TEXT_UNVALIDATED","scope":"EN_ONLY"}
    from nox_prime_soul_stage1_train import featurize, GROUPS
    net,accepted,torch=_model(root)
    if net is None:return {"available":False,"reason":"NO_ACCEPTED_WEIGHTS","scope":"EN_ONLY"}
    ids=torch.tensor(featurize(text),dtype=torch.long)
    offsets=torch.tensor([0],dtype=torch.long)
    with torch.no_grad():
        probabilities=net(ids,offsets).sigmoid().tolist()[0]
    scores={k:round(float(v),4) for k,v in zip(GROUPS,probabilities)}
    selected=[k for k,p in scores.items() if p>=accepted["threshold"]]
    return {"available":True,"scope":"EN_ONLY",
            "model_sha256":accepted["sha256"],
            "labels":selected,
            "scores":scores,
            "test_micro_f1":accepted["test_micro_f1"],
            "interpretation":"fallible emotion cues in English text only; not experienced emotions",
            "connected_to_main_llm":False}
