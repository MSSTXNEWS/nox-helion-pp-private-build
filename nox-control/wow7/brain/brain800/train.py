"""Offline training. NumPy is an optional dependency of the small router only."""
import argparse
from collections import Counter
import hashlib
import importlib
import json
from pathlib import Path
import tempfile

from .kernel import Kernel, MODULES
from . import features, neural, corpus
import numpy as np

def identities(kernel):
    ids=sorted(kernel.meta)
    enc=neural.encoder_fingerprint({"version":features.ENCODER_ID,"columns":list(features.FEATURE_NAMES)})
    return ids,neural.catalog_fingerprint(ids),enc

def registry_examples(kernel,ids):
    # The encoder reads only top-level field presence. No example payload values enter training.
    schemas={}
    for domain in MODULES:
        mod=importlib.import_module("."+domain,__package__)
        for key in mod.OPS:
            name=key if key.startswith(domain+".") else domain+"."+key
            example=getattr(mod,"SAMPLES",{}).get(key,getattr(mod,"SAMPLE",{}))
            schemas[name]={k:True for k,v in example.items() if v is not None}
    rows=[]
    for name in ids:
        fields=schemas.get(name,{"key":True,"source":True})
        title=kernel.meta[name]
        if name=="perception.document.tasks": title+="\n- Закончить эскиз"
        if name=="perception.document.numbers": title+=" в 10:30"
        rows.append({"text":title,"data":fields,"op":name})
    return rows

def train(args):
    k=Kernel("unused")
    ids,cat,enc=identities(k)
    rows=corpus.load_rows(args.corpus,ids) if args.corpus else corpus.seed_rows()
    train_rows,held=corpus.split_rows(rows,seed=args.seed,validation_fraction=.20)
    if not train_rows or not held:raise ValueError("Нужны непересекающиеся train и holdout")
    holdtext={r["text"].casefold().strip() for r in held}
    weak=[r for r in registry_examples(k,ids) if r["text"].casefold().strip() not in holdtext]
    training = weak+train_rows*6 if not args.base else train_rows
    def arrays(items):
        return (np.asarray([features.encode(r["text"],r.get("data") or {}) for r in items],dtype=float),
                np.asarray([ids.index(r["op"]) for r in items],dtype=int))
    x,y=arrays(training);v,t=arrays(held)
    model=neural.Router.load(args.base,cat,enc) if args.base else neural.Router(seed=args.seed)
    if args.base:model.enable_lora(rank=args.rank,seed=args.seed)
    def scores(a,b):
        pred=np.asarray(model.logits(a))
        return {"top1":int(np.sum(np.argmax(pred,axis=1)==b)),"top5":int(sum(label in row for label,row in zip(b,np.argsort(-pred,axis=1)[:,:5]))),"n":len(b)}
    baseline=scores(v,t)
    rng=np.random.default_rng(args.seed)
    loss=None
    for epoch in range(args.epochs):
        order=rng.permutation(len(y))
        for pos in range(0,len(y),32):
            ix=order[pos:pos+32]
            loss=(model.train_lora_batch if args.base else model.train_batch)(x[ix],y[ix],lr=args.lr)
    out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=out.parent,suffix=".npz",delete=False) as temp:
        staged=Path(temp.name)
    try:
        model.save(staged,cat,enc)
        reloaded=neural.Router.load(staged,cat,enc)
        if not np.allclose(model.logits(v),reloaded.logits(v)):raise ValueError("Checkpoint mismatch")
        staged.replace(out)
    finally:
        staged.unlink(missing_ok=True)
    summary={"kind":"adapter" if args.base else "base","base_parameters":10000,
        "extra_adapter_parameters":810*args.rank if args.base else 0,"seed":args.seed,
        "epochs":args.epochs,"learning_rate":args.lr,"weak_catalog_descriptions":0 if args.base else len(weak),
        "user_verified_labels":0 if not args.corpus else None,
        "authored_or_optin_train":len(train_rows),"distinct_train_ops":len(set(y)),
        "nonzero_input_columns":int(np.any(x!=0,axis=0).sum()),
        "holdout_distinct_ops":len(set(t)),"holdout_before":baseline,"holdout_after":scores(v,t),
        "last_minibatch_loss":float(loss),"catalog_fingerprint":cat,"encoder_fingerprint":enc,
        "checkpoint_sha256":hashlib.sha256(out.read_bytes()).hexdigest(),"mode":"suggest_only"}
    print(json.dumps(summary,ensure_ascii=False,indent=2))
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out",required=True);p.add_argument("--corpus");p.add_argument("--base")
    p.add_argument("--rank",type=int,default=4);p.add_argument("--epochs",type=int,default=100)
    p.add_argument("--lr",type=float,default=0.25);p.add_argument("--seed",type=int,default=1807)
    args=p.parse_args()
    if args.epochs<1 or args.lr<=0:p.error("epochs and lr must be positive")
    train(args)
if __name__=="__main__":main()
