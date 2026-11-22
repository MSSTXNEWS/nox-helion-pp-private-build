"""Read-only inference. Ranking an operation never executes it."""
import os
from pathlib import Path
import numpy as np
from .train import identities
from .features import encode
from .neural import Router

def suggest(kernel, text, data=None, scope=""):
    if not isinstance(text,str) or not text.strip():raise ValueError("Введите задачу для подбора операции")
    ids,cat,enc=identities(kernel)
    checkpoint=os.environ.get("NOX_BRAIN800_ROUTER") or Path(__file__).with_name("router10k.npz")
    if scope and scope!="default":
        from .evolve import active_checkpoint
        checkpoint=active_checkpoint(kernel.path.parent/"brain800-evolution",scope,checkpoint)
    model=Router.load(checkpoint,cat,enc)
    x=np.array([encode(text,data or {})])
    raw=model.logits(x)[0]
    return [{"op":ids[i],"description":kernel.meta[ids[i]],"score":round(float(raw[i]),4)} for i in np.argsort(-raw)[:5]]
