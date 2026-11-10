"""NOX SOUL Stage-1 genuine small neural affect learner (CPU-first).
It trains NEW trainable weights on public, source-pinned GoEmotions EN only.
It NEVER overwrites LoRA, existing S03, persona data, or base Ollama models.
A model trained on English is NOT claimed as RU/ES or subjective consciousness.
"""
from __future__ import annotations
import argparse, hashlib, json, math, os, re, secrets, sys, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

DATASET_REPO="google-research/google-research"
DATASET_SUBPATH="goemotions/data"
NAMES=("train.tsv","dev.tsv","test.tsv","emotions.txt")
GROUPS={
 "positive":(0,1,4,13,15,17,18,20,21,23),
 "negative":(2,3,9,10,11,12,14,16,19,24,25),
 "curiosity":(6,7,22),
 "caring":(5,18),
 "surprise":(26,),
 "neutral":(27,),
}
VOCAB=16384
EMBED=48
MAX_BYTES={"train.tsv":12_000_000,"dev.tsv":3_000_000,"test.tsv":3_000_000,"emotions.txt":8000}
def utc():
    return datetime.now(timezone.utc).isoformat()
def sha_file(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1048576),b""):h.update(b)
    return h.hexdigest()
def safe_json(path, obj):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name("."+path.name+"."+str(os.getpid())+".tmp")
    tmp.write_text(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2),encoding="utf-8")
    os.replace(tmp,path)
def _get(url,max_bytes):
    req=Request(url,headers={"User-Agent":"NOX-HELION-SOUL-Stage1/1"})
    with urlopen(req,timeout=45) as r:
        data=r.read(max_bytes+1)
    if not data or len(data)>max_bytes:
        raise RuntimeError("Invalid/oversized official dataset response")
    return data
def load_data(root):
    folder=root/"datasets"/"goemotions"
    manifest=folder/"SOURCE_MANIFEST.json"
    if manifest.is_file():
        obj=json.loads(manifest.read_text(encoding="utf-8"))
        if obj.get("source_repo")!=DATASET_REPO or not re.fullmatch(r"[a-f0-9]{40}",str(obj.get("revision",""))):
            raise RuntimeError("Invalid existing dataset source manifest")
        for name in NAMES:
            p=folder/name
            if not p.is_file() or sha_file(p)!=obj.get("sha256",{}).get(name):
                raise RuntimeError("Existing dataset HASH_MISMATCH/HOLD: "+str(p))
        print("NOX DATASET: verified local copy",obj["revision"],flush=True)
        return folder,obj
    if folder.exists() and any(folder.iterdir()):
        raise RuntimeError("Existing GoEmotions files lack approved SHA manifest; no overwrite")
    folder.mkdir(parents=True,exist_ok=True)
    # GitHub commit is resolved before downloading, then all four files use that
    # IMMUTABLE revision; no unversioned training dataset.
    api="https://api.github.com/repos/"+DATASET_REPO+"/commits/master"
    info=json.loads(_get(api,600_000))
    rev=str(info.get("sha",""))
    if not re.fullmatch("[a-f0-9]{40}",rev):raise RuntimeError("Unable to pin GoEmotions commit")
    base="https://raw.githubusercontent.com/"+DATASET_REPO+"/"+rev+"/"+DATASET_SUBPATH+"/"
    hashes={}
    try:
        for name in NAMES:
            data=_get(base+name,MAX_BYTES[name])
            tmp=folder/(name+".partial")
            tmp.write_bytes(data)
            if name=="train.tsv" and data.count(b"\n")<40000:
                raise RuntimeError("Unexpected train dataset shape")
            os.replace(tmp,folder/name)
            hashes[name]=sha_file(folder/name)
    except Exception:
        # Preserve partial evidence for diagnosis; never silently replace a download.
        raise
    obj={"source_repo":DATASET_REPO,"revision":rev,"license_claim":"Apache-2.0 repository; Reddit-origin research corpus",
         "split":"official simplified train/dev/test","sha256":hashes,"downloaded_utc":utc()}
    safe_json(manifest,obj)
    return folder,obj
def parse_split(path):
    values=[]
    seen=set()
    with Path(path).open("r",encoding="utf-8") as f:
        for n,line in enumerate(f,1):
            parts=line.rstrip("\r\n").split("\t")
            if len(parts)!=3:raise RuntimeError("Malformed dataset row %s:%d"%(path,n))
            sentence,labels,uid=parts
            if not sentence or not uid or uid in seen:
                raise RuntimeError("Invalid/duplicate example ID at line "+str(n))
            seen.add(uid)
            try: lab={int(z) for z in labels.split(",")}
            except ValueError as e:raise RuntimeError("Invalid label at line "+str(n)) from e
            if not lab or min(lab)<0 or max(lab)>27:
                raise RuntimeError("Out-of-range emotion label at "+str(n))
            target=[1.0 if (lab & set(GROUPS[k])) else 0.0 for k in GROUPS]
            values.append((sentence,target,uid))
    if not values:raise RuntimeError("Empty split "+str(path))
    return values
def featurize(sentence):
    tokens=re.findall(r"\w+|[^\w\s]",sentence.lower(),flags=re.UNICODE)[:100]
    if not tokens: tokens=["?"]
    gram=tokens+[" ".join(tokens[i:i+2]) for i in range(len(tokens)-1)]
    return [int.from_bytes(hashlib.blake2b(x.encode("utf-8"),digest_size=4).digest(),"little")%VOCAB
            for x in gram[:180]]
def examples(split):
    return [(featurize(s),label) for s,label,_ in split]
def _collate(batch):
    import torch
    ids,offsets,labels=[],[],[]
    for tok,l in batch:
        offsets.append(len(ids))
        ids.extend(tok)
        labels.append(l)
    return (torch.tensor(ids,dtype=torch.long),
            torch.tensor(offsets,dtype=torch.long),
            torch.tensor(labels,dtype=torch.float32))
def _net():
    import torch
    from torch import nn
    class AffectNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.embed=nn.EmbeddingBag(VOCAB,EMBED,mode="mean")
            self.head=nn.Sequential(nn.Linear(EMBED,64),nn.GELU(),nn.Linear(64,len(GROUPS)))
        def forward(self,ids,offsets):
            return self.head(self.embed(ids,offsets))
    return AffectNet()
def score(probs,truth,threshold):
    tp=fp=fn=0
    for out,labels in zip(probs,truth):
        for v,y in zip(out,labels):
            guess=v>=threshold
            tp+=bool(guess and y)
            fp+=bool(guess and not y)
            fn+=bool((not guess) and y)
    return 2*tp/(2*tp+fp+fn) if (2*tp+fp+fn)>0 else 0.0
def baseline(truth):
    idx=list(GROUPS).index("neutral")
    probs=[[1.0 if i==idx else 0.0 for i in range(len(GROUPS))] for _ in truth]
    return score(probs,truth,.5)
def _predict(net, dataset, batch_size=256):
    import torch
    from torch.utils.data import DataLoader
    net.eval()
    probs=[]
    truth=[]
    with torch.no_grad():
        for ids,offsets,y in DataLoader(dataset,batch_size=batch_size,collate_fn=_collate):
            out=net(ids,offsets).sigmoid().cpu().tolist()
            probs.extend(out)
            truth.extend(y.cpu().tolist())
    return probs,truth
def train(root,epochs=2):
    import torch
    from torch.utils.data import DataLoader
    from safetensors.torch import save_file,load_file
    if not (1<=epochs<=4):raise ValueError("1..4 CPU epochs")
    root=Path(root).resolve()
    if not (root/"brain").is_dir():raise RuntimeError("Expected existing NOX_NEW/brain root")
    torch.set_num_threads(2)  # CPU-only: do NOT borrow GPU from Ollama/SAFE70.
    torch.manual_seed(20261107)
    folder,manifest=load_data(root)
    splits={name:parse_split(folder/name) for name in ("train.tsv","dev.tsv","test.tsv")}
    if set(z[2] for z in splits["train.tsv"]) & set(z[2] for z in splits["dev.tsv"]):
        raise RuntimeError("TRAIN/DEV_LEAKAGE")
    if set(z[2] for z in splits["train.tsv"]) & set(z[2] for z in splits["test.tsv"]):
        raise RuntimeError("TRAIN/TEST_LEAKAGE")
    tr,dev,test=(examples(splits[x]) for x in ("train.tsv","dev.tsv","test.tsv"))
    outdir=root/"brain"/"intelligence"/"soul_stage1"
    run=outdir/("run_"+datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")+"_"+secrets.token_hex(3))
    run.mkdir(parents=True,exist_ok=False)
    net=_net() # stays on CPU, no .cuda() or torch_directml calls.
    opt=torch.optim.AdamW(net.parameters(),lr=0.004,weight_decay=0.001)
    best=None
    for epoch in range(1,epochs+1):
        net.train()
        accumulated=0.0
        count=0
        loader=DataLoader(tr,batch_size=256,shuffle=True,collate_fn=_collate)
        for ids,offsets,y in loader:
            opt.zero_grad(set_to_none=True)
            loss=torch.nn.functional.binary_cross_entropy_with_logits(net(ids,offsets),y)
            if not torch.isfinite(loss):
                raise RuntimeError("Training loss invalid")
            loss.backward()
            opt.step()
            accumulated+=float(loss.item())
            count+=1
        dp,dy=_predict(net,dev)
        trial=[(score(dp,dy,t),t) for t in (.2,.25,.3,.35,.4,.45,.5)]
        dev_f1,threshold=max(trial)
        print("NOX SOUL CPU EPOCH",epoch,"loss",round(accumulated/count,5),
              "dev_micro_f1",round(dev_f1,4),"threshold",threshold,flush=True)
        if best is None or dev_f1>best[0]:
            best=(dev_f1,threshold,epoch)
            save_file({k:v.detach().cpu().contiguous() for k,v in net.state_dict().items()},
                      str(run/"best.safetensors"))
    state=load_file(str(run/"best.safetensors"),device="cpu")
    net.load_state_dict(state,strict=True)
    probs,truth=_predict(net,test)
    test_f1=score(probs,truth,best[1])
    base_f1=baseline(truth)
    passed=math.isfinite(test_f1) and test_f1>=base_f1+.02 and best[0]>=.25
    weights=run/"best.safetensors"
    evidence={"status":"HOLDOUT_PASSED" if passed else "RESEARCH_CANDIDATE_HOLD",
              "scope":"English emotion-context prototype only; NOT human feelings or RU/ES",
              "architecture":"EmbBag-16384x48→MLP64→6-sigmoid; CPU PyTorch",
              "classes":list(GROUPS),"training_source":manifest,
              "train_rows":len(tr),"dev_rows":len(dev),"test_rows":len(test),
              "epochs_attempted":epochs,"best_epoch":best[2],
              "dev_micro_f1":round(best[0],5),
              "test_micro_f1":round(test_f1,5),
              "neutral_only_baseline_f1":round(base_f1,5),
              "decision_threshold":best[1],"weights_sha256":sha_file(weights),
              "completed_utc":utc(),
              "note":"candidate not plugged into canonical S03 nor qwen3:8b"}
    safe_json(run/"TRAINING_EVIDENCE.json",evidence)
    if passed:
        current=outdir/"CURRENT_VERIFIED.json"
        promote=True
        if current.is_file():
            prev=json.loads(current.read_text(encoding="utf-8"))
            if float(prev.get("test_micro_f1",0))>=test_f1:promote=False
        if promote:
            safe_json(current,{"model_path":str(weights),"model_sha256":sha_file(weights),
                               "test_micro_f1":test_f1,"source_run":run.name,
                               "promoted_utc":utc()})
    print("NOX STAGE1 NEW NEURAL WEIGHTS",weights,flush=True)
    print("NOX TRAIN RESULT",json.dumps({k:v for k,v in evidence.items() if k!="training_source"}),flush=True)
    return evidence
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=Path(r"C:\NOX_HELION\NOX_NEW"))
    parser.add_argument("--epochs",type=int,default=2)
    args=parser.parse_args()
    try:
        train(args.root,args.epochs)
    except Exception as ex:
        print("NOX SOUL NEW TRAINING HOLD:",type(ex).__name__,str(ex),file=sys.stderr,flush=True)
        raise SystemExit(1)
