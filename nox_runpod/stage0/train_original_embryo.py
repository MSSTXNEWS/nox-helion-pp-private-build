#!/usr/bin/env python3
"""Continue training the ORIGINAL NOX Embryo weights on teacher-generated text.
Never writes original checkpoints and never claims complete 9B absorption.
"""
import argparse, hashlib, importlib.util, inspect, json, os, pathlib, random, sys, traceback
import torch
from torch import nn
from safetensors.torch import load_file, save_file

ROOT=pathlib.Path("/workspace/nox")
E=ROOT/"embryo/NOX_EMBRYO_TRANSFER_STAGE"
OUT=ROOT/"checkpoints/nox_genesis_stage0"
SOURCE=ROOT/"distillation/embryo_v1/9b_teacher_corpus.jsonl"

def digest(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for part in iter(lambda:f.read(4*1024*1024),b""):h.update(part)
    return h.hexdigest()
def load_rows():
    if not SOURCE.is_file():raise RuntimeError("Missing real teacher-generated data")
    records={}
    for line in SOURCE.read_text(encoding="utf-8").splitlines():
        try:
            row=json.loads(line)
            if row.get("teacher")!="LOCAL_QWEN3.5_9B" or len(row.get("text",""))<80:
                continue
            records[row["id"]]=row
        except (ValueError,KeyError):pass
    if len(records)<24:raise RuntimeError(f"Teacher dataset too small: {len(records)}; need >=24 real records")
    return [records[k]["text"] for k in sorted(records)]
def load_embryo():
    config_file=E/"model_config.json"
    code_file=E/"model.py"
    if not config_file.is_file() or not code_file.is_file():
        raise RuntimeError("Original model.py/model_config.json absent; cannot instantiate original embryo")
    config=json.loads(config_file.read_text(encoding="utf-8"))
    if not isinstance(config,dict):raise RuntimeError("Invalid original model config")
    sys.path.insert(0,str(E))
    spec=importlib.util.spec_from_file_location("nox_embryo_original_model",str(code_file))
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    candidate_classes=[(name,cls) for name,cls in vars(module).items()
                       if inspect.isclass(cls) and issubclass(cls,nn.Module) and cls is not nn.Module and cls.__module__==module.__name__]
    if not candidate_classes:raise RuntimeError("Original model.py defines no torch.nn.Module model")
    weight_paths=sorted(E.rglob("*.safetensors"))
    # Original is immutable. Prefer explicitly the latest original embryo candidate with readable weights.
    if not weight_paths:raise RuntimeError("Original Embryo safetensors checkpoint missing")
    def instantiate(cls):
        sig=inspect.signature(cls)
        kwargs={}
        for name,param in sig.parameters.items():
            if name=="self":continue
            if name in config:kwargs[name]=config[name]
            elif name in ("config","cfg","model_config"):kwargs[name]=config
            elif param.default is inspect.Parameter.empty:raise TypeError("Unknown required model argument: "+name)
        return cls(**kwargs)
    errors=[]
    for path in sorted(weight_paths,key=lambda p:p.stat().st_mtime,reverse=True):
        try: weights=load_file(str(path),device="cpu")
        except Exception as e:errors.append(f"{path.name}: {str(e)[:90]}");continue
        state_variants=[weights]
        for prefix in ("model.","module.","net."):
            if any(k.startswith(prefix) for k in weights):
                state_variants.append({k[len(prefix):] if k.startswith(prefix) else k:v for k,v in weights.items()})
        for name,cls in candidate_classes:
            try:
                model=instantiate(cls)
                for state in state_variants:
                    result=model.load_state_dict(state,strict=False)
                    total=len(model.state_dict())
                    matched=total-len(result.missing_keys)
                    if matched<max(2,int(0.9*total)):continue
                    if result.missing_keys or result.unexpected_keys:
                        continue # fail-closed: do not silently reinitialize embryo layers
                    return model,path,config,name
            except Exception as e:errors.append(f"{name}:{str(e)[:120]}")
    raise RuntimeError("Cannot load original Embryo strictly; not recreating model: "+"; ".join(errors[:8]))
def logits_from(model,tokens):
    try:out=model(tokens)
    except TypeError:out=model(input_ids=tokens)
    if isinstance(out,dict): out=out.get("logits")
    if hasattr(out,"logits"):out=out.logits
    if isinstance(out,(tuple,list)):out=out[0]
    if not isinstance(out,torch.Tensor):raise RuntimeError("Original embryo forward does not return logits")
    if out.ndim!=3:raise RuntimeError(f"Expected [batch,seq,vocab] logits, received {tuple(out.shape)}")
    return out
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--steps",type=int,default=120)
    ap.add_argument("--context",type=int,default=128)
    ap.add_argument("--resume",default=None,help="Prior verified NOX Embryo safetensors checkpoint")
    ap.add_argument("--out",default=str(OUT))
    ap.add_argument("--lr",type=float,default=8e-5)
    ap.add_argument("--checkpoint-every",type=int,default=10)
    args=ap.parse_args()
    if not 1<=args.steps<=5000:raise RuntimeError("Invalid optimizer steps")
    if not 16<=args.context<=256:raise RuntimeError("Invalid sequence length")
    if not 1<=args.checkpoint_every<=args.steps:raise RuntimeError("Invalid checkpoint interval")
    if not torch.cuda.is_available():raise RuntimeError("No NVIDIA GPU")
    device=torch.device("cuda:0")
    if not (0 < args.lr <= 0.001):raise RuntimeError("Unsafe LR")
    rows=load_rows()
    model,src,config,classname=load_embryo()
    if args.resume:
        previous=pathlib.Path(args.resume)
        if not previous.is_file():raise RuntimeError("Resume checkpoint missing")
        model.load_state_dict(load_file(str(previous),device="cpu"),strict=True)
        print(json.dumps({"event":"RESUMED_FROM_NOX_CHECKPOINT","sha256":digest(previous)}),flush=True)
    model=model.to(device)
    model.train()
    # Original embryo uses its own tokenizer/vocab. Byte mapping is valid only when vocab >= 256.
    sample=logits_from(model,torch.zeros((1,16),dtype=torch.long,device=device))
    vocab=sample.shape[-1]
    if vocab<256:raise RuntimeError(f"Embryo vocab={vocab} <256; need original tokenizer, no guessed mapping")
    if vocab>256:
        print(json.dumps({"warning":"Byte-level UTF8 learning is provisional; Embryo native tokenizer may differ. No full absorption claim."}),flush=True)
    weights_initial=[p.detach().cpu().clone() for p in model.parameters() if p.requires_grad]
    if not weights_initial:raise RuntimeError("Embryo has no trainable parameters")
    tokens=[]
    for s in rows:
        # UTF8 byte tokens, no fabricated teacher examples
        bytes_list=list(s.encode("utf-8"))
        for i in range(0,len(bytes_list)-args.context-1,args.context):
            tokens.append(bytes_list[i:i+args.context+1])
    if len(tokens)<8:raise RuntimeError("Too few real token sequences")
    random.Random(42).shuffle(tokens)
    holdout=tokens[:max(2,len(tokens)//10)]
    train=tokens[len(holdout):]
    def loss_for(batch):
        tensor=torch.tensor(batch,dtype=torch.long,device=device)
        pred=logits_from(model,tensor[:,:-1])
        return nn.functional.cross_entropy(pred.float().reshape(-1,pred.size(-1)),tensor[:,1:].reshape(-1))
    def evaluate():
        model.eval()
        with torch.no_grad():vals=[float(loss_for([b]).item()) for b in holdout[:8]]
        model.train()
        return sum(vals)/len(vals)
    before=evaluate()
    opt=torch.optim.AdamW([p for p in model.parameters() if p.requires_grad],lr=args.lr)
    output=pathlib.Path(args.out)
    output.mkdir(parents=True,exist_ok=True)
    print(json.dumps({"event":"NOX_EMBRYO_TRAIN_BEGIN","original":str(src),"model_class":classname,
                      "teacher_records":len(rows),"training_batches":len(train),"vocab":vocab,
                      "holdout_loss_before":before}),flush=True)
    checkpoint=output/"embryo_stage0_trained.safetensors"
    log=output/"training_steps.jsonl"
    resume_weights=output/"in_progress.safetensors"
    resume_state=output/"in_progress.pt"
    start_step=0
    if resume_weights.is_file() and resume_state.is_file() and not checkpoint.is_file():
        saved=torch.load(str(resume_state),map_location="cpu",weights_only=True)
        meta={"source_sha256":digest(src),"dataset_sha256":digest(SOURCE),
              "steps_target":args.steps,"context":args.context,"learning_rate":args.lr}
        if any(saved.get(k)!=v for k,v in meta.items()):
            raise RuntimeError("Existing training state belongs to different source/dataset/config")
        if digest(resume_weights)!=saved.get("weights_sha256"):
            raise RuntimeError("Checkpoint/resume state checksum mismatch")
        model.load_state_dict(load_file(str(resume_weights),device="cpu"),strict=True)
        opt.load_state_dict(saved["optimizer"])
        start_step=int(saved["completed_steps"])
        if not 0<=start_step<args.steps:raise RuntimeError("Invalid saved step")
        print(json.dumps({"event":"AUTO_RESUME","step":start_step}),flush=True)
    best=float("inf");steps=start_step
    for step in range(start_step+1,args.steps+1):
        seq=train[(step-1)%len(train)]
        opt.zero_grad(set_to_none=True)
        loss=loss_for([seq])
        if not torch.isfinite(loss):raise RuntimeError("Non-finite training loss")
        loss.backward()
        norm=torch.nn.utils.clip_grad_norm_(model.parameters(),1.)
        if not torch.isfinite(norm):raise RuntimeError("Non-finite gradient norm")
        opt.step()
        steps=step
        if step % args.checkpoint_every == 0 and step < args.steps:
            intermediate={k:v.detach().cpu().contiguous() for k,v in model.state_dict().items()
                          if torch.is_tensor(v)}
            tmp=output/"in_progress.tmp.safetensors"
            save_file(intermediate,str(tmp))
            os.replace(tmp,resume_weights)
            meta={"source_sha256":digest(src),"dataset_sha256":digest(SOURCE),
                  "steps_target":args.steps,"context":args.context,"learning_rate":args.lr,
                  "completed_steps":step,"weights_sha256":digest(resume_weights),
                  "optimizer":opt.state_dict()}
            stmp=output/"in_progress.tmp.pt"
            torch.save(meta,str(stmp))
            os.replace(stmp,resume_state)
            print(json.dumps({"event":"STEP_CHECKPOINT","step":step,"sha256":meta["weights_sha256"]}),flush=True)
        if step%10==0 or step==1 or step==args.steps:
            value=evaluate()
            event={"step":step,"train_loss":float(loss.item()),"holdout_loss":value}
            with log.open("a",encoding="utf-8") as f:f.write(json.dumps(event)+"\n")
            print(json.dumps(event),flush=True)
            if value<best:best=value
    after=evaluate()
    changed=sum(int(not torch.equal(a,p.detach().cpu())) for a,p in zip(weights_initial,[p for p in model.parameters() if p.requires_grad]))
    if not changed:raise RuntimeError("NO PARAMETERS UPDATED. NOT TRAINED")
    model.eval()
    weights={k:v.detach().cpu().contiguous() for k,v in model.state_dict().items() if torch.is_tensor(v)}
    temp=output/"embryo_stage0_trained.tmp.safetensors"
    save_file(weights,str(temp))
    check=load_file(str(temp),device="cpu")
    if set(check)!=set(weights):raise RuntimeError("Checkpoint readback mismatch")
    os.replace(temp,checkpoint)
    if resume_state.exists(): resume_state.unlink()
    if resume_weights.exists(): resume_weights.unlink()
    receipt={"status":"TRAINED_NOT_INDEPENDENTLY_VALIDATED","utc":__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
         "teacher":"LOCAL_QWEN3.5_9B","original_embryo_checkpoint":str(src),"original_sha256":digest(src),
         "checkpoint":str(checkpoint),"checkpoint_sha256":digest(checkpoint),
         "teacher_dataset_sha256":digest(SOURCE),"teacher_records":len(rows),"steps":steps,
         "parameters_changed":changed,"holdout_loss_before":before,"holdout_loss_after":after,
         "identity":"NOX_EMBRYO_V1","birth_recorded":False}
    (output/"stage0_receipt.json").write_text(json.dumps(receipt,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps(receipt,ensure_ascii=False),flush=True)
if __name__=="__main__":
    try:main()
    except Exception as ex:
        print("NOX_EMBRYO_TRAIN_FAILED: "+repr(ex),file=sys.stderr,flush=True)
        raise
