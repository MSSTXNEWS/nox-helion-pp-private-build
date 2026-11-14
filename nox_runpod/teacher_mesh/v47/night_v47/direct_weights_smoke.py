#!/usr/bin/env python3
"""NOX V47 — genuine *base-weight* FP16 optimizer smoke on V100 GPU1.

This tool never trains GGUF, never writes the active live model, never promotes
anything to chat and never downloads weights. It trains one existing final base
transformer layer (not a LoRA adapter) for 1..20 audited steps, checkpoints
HF weights + optimizer state and reopens the checkpoint for evaluation.

It MUST be called by an authorized existing OneHost, from a vetted environment,
after offsite snapshot+restore validation and dataset privacy/license audit.
This script is not an installer, supervisor, SSH bridge or production trainer.
"""
from __future__ import annotations
import argparse, datetime as dt, gc, hashlib, json, os, pathlib, shutil, sys, tempfile


def sha_file(path, chunk=4*1024*1024):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        while True:
            b=f.read(chunk)
            if not b:break
            h.update(b)
    return h.hexdigest()


def read_samples(path, label):
    p=pathlib.Path(path)
    if not p.is_file() or p.stat().st_size>25*1024*1024:
        raise RuntimeError('HOLD_'+label+'_FILE_MISSING_OR_TOO_LARGE')
    samples=[]; sources=set()
    with p.open(encoding='utf-8') as f:
        for line in f:
            if not line.strip():continue
            row=json.loads(line)
            if not isinstance(row,dict) or any(k not in row for k in ('prompt','completion','source_uri')):
                raise RuntimeError('HOLD_INVALID_'+label+'_ROW')
            q,a,src=row['prompt'],row['completion'],row['source_uri']
            if not all(isinstance(x,str) and x.strip() for x in (q,a,src)):
                raise RuntimeError('HOLD_EMPTY_'+label+'_ROW')
            if len(q)>5000 or len(a)>9000 or len(src)>300:
                raise RuntimeError('HOLD_OVERSIZE_'+label+'_ROW')
            if row.get('rights_verified') is not True or row.get('privacy_approved') is not True:
                raise RuntimeError('HOLD_LICENSE_OR_PRIVACY_'+label)
            samples.append(row);sources.add(src)
            if len(samples)>2048:raise RuntimeError('HOLD_TOO_MANY_SAMPLES')
    if len(samples)<4:raise RuntimeError('HOLD_INSUFFICIENT_'+label+'_SAMPLES')
    return samples,sources


def model_manifest_bytes(folder):
    """Conservative space estimate: sum local .safetensors/.bin snapshot weights only."""
    root=pathlib.Path(folder)
    if not root.is_dir() or not (root/'config.json').is_file():
        raise RuntimeError('HOLD_LOCAL_TRAINABLE_HF_MODEL_NOT_FOUND')
    shards=list(root.glob('*.safetensors'))+list(root.glob('pytorch_model*.bin'))
    if not shards:raise RuntimeError('HOLD_GGUF_OR_NO_TRAINABLE_SHARDS')
    return sum(p.stat().st_size for p in shards)


def select_last_block(model):
    import torch
    choices=[]
    for name,mod in model.named_modules():
        if isinstance(mod,torch.nn.ModuleList) and len(mod)>=8:
            if all(any(hasattr(x,t) for t in ('self_attn','attn','attention')) for x in list(mod)[-2:]):
                choices.append((name,mod))
    if not choices:
        raise RuntimeError('HOLD_TRANSFORMER_LAYER_STRUCTURE_UNSUPPORTED')
    # Deepest module first; if equally deep, reject ambiguity rather than change wrong tensor.
    choices.sort(key=lambda x:(x[0].count('.'),len(x[1])),reverse=True)
    if len(choices)>1 and choices[1][0].count('.')==choices[0][0].count('.'):
        raise RuntimeError('HOLD_AMBIGUOUS_TRANSFORMER_BLOCKS')
    name,layers=choices[0]
    for p in model.parameters():p.requires_grad_(False)
    for p in layers[-1].parameters():p.requires_grad_(True)
    return name+'.'+str(len(layers)-1),[p for p in layers[-1].parameters() if p.requires_grad]


def trainable_tensor_digest(params):
    """Hash every direct base-weight tensor in bounded CPU chunks."""
    import torch
    h=hashlib.sha256()
    for p in params:
        v=p.detach().flatten()
        for sl in v.split(262144):
            buf=sl.float().cpu().numpy().tobytes()
            h.update(buf)
    return h.hexdigest()


def item_loss(model, tokenizer, device, row, max_tokens):
    import torch
    q,a=row['prompt'],row['completion']
    if not getattr(tokenizer,'chat_template',None):
        raise RuntimeError('HOLD_TOKENIZER_CHAT_TEMPLATE_MISSING')
    prompt=tokenizer.apply_chat_template([{'role':'user','content':q}],tokenize=False,add_generation_prompt=True)
    prefix=tokenizer(prompt,add_special_tokens=False)['input_ids']
    eos=tokenizer.eos_token or ''
    target=tokenizer(a+eos,add_special_tokens=False)['input_ids']
    # Fit prompt and target independently; reserve >= 16 response tokens.
    max_prompt=max(16,max_tokens-64)
    prefix=prefix[-max_prompt:]
    target=target[:max_tokens-len(prefix)]
    if len(target)<2:raise RuntimeError('HOLD_TARGET_TRUNCATED')
    all_ids=prefix+target
    labels=[-100]*len(prefix)+target
    x=torch.tensor([all_ids],device=device,dtype=torch.long)
    y=torch.tensor([labels],device=device,dtype=torch.long)
    result=model(input_ids=x,attention_mask=torch.ones_like(x),labels=y,use_cache=False)
    return result.loss


def mean_holdout_loss(model,tokenizer,device,rows,max_tokens):
    import torch
    model.eval()
    vals=[]
    with torch.no_grad():
        for row in rows[:8]:
            loss=item_loss(model,tokenizer,device,row,max_tokens)
            if not torch.isfinite(loss):raise RuntimeError('HOLD_NONFINITE_HOLDOUT_LOSS')
            vals.append(float(loss.item()))
    return sum(vals)/len(vals)


def gpu_guards():
    import torch
    if not torch.cuda.is_available() or torch.cuda.device_count()!=2:
        raise RuntimeError('HOLD_TWO_PHYSICAL_V100_GPU_REQUIRED')
    if torch.cuda.get_device_capability(1)!=(7,0) or 'V100' not in torch.cuda.get_device_name(1):
        raise RuntimeError('HOLD_GPU1_MUST_BE_V100_SM70')
    if not (torch.version.cuda or '').startswith('12.'):
        raise RuntimeError('HOLD_TORCH_CUDA12_SM70_REQUIRED')
    # Runtime memory check; leave at least 3GiB on GPU1 after model load.
    free,total=torch.cuda.mem_get_info(1)
    return free,total


def run(args):
    if not args.execute or os.getenv('NOX_ONEHOST_NATIVE_APPROVED')!='1':
        raise RuntimeError('HOLD_ONEHOST_NATIVE_APPROVAL_REQUIRED')
    if not 1<=args.steps<=20 or not 64<=args.max_tokens<=384:
        raise RuntimeError('HOLD_UNSAFE_STEP_OR_TOKEN_LIMIT')
    student=pathlib.Path(args.student).resolve()
    out=pathlib.Path(args.out).resolve()
    if out.exists() or out==student or student in out.parents:
        raise RuntimeError('HOLD_OUTPUT_OVERWRITE_OR_INSIDE_STUDENT')
    if not out.parent.is_dir():raise RuntimeError('HOLD_OUTPUT_PARENT_REQUIRED')
    weights_bytes=model_manifest_bytes(student)
    space=shutil.disk_usage(out.parent).free
    if space<weights_bytes*1.3 + 20_000_000_000:
        raise RuntimeError('HOLD_CHECKPOINT_DISK_SPACE')
    train,train_sources=read_samples(args.train,'TRAIN')
    holdout,held_sources=read_samples(args.holdout,'HOLDOUT')
    if train_sources & held_sources:
        raise RuntimeError('HOLD_TRAIN_HOLDOUT_SOURCE_LEAKAGE')
    if args.stop_file and pathlib.Path(args.stop_file).exists():
        raise RuntimeError('HOLD_STOP_ACTIVE')
    import torch
    from transformers import AutoTokenizer,AutoModelForCausalLM
    torch.manual_seed(3407)
    free,total=gpu_guards()
    if free < weights_bytes*1.1 + 3*1024**3:
        raise RuntimeError('HOLD_GPU1_VRAM_ESTIMATE')
    device=torch.device('cuda:1')
    # No trust_remote_code and no network: user must have supplied vetted local HF weights.
    tokenizer=AutoTokenizer.from_pretrained(str(student),local_files_only=True,trust_remote_code=False)
    model=AutoModelForCausalLM.from_pretrained(str(student),local_files_only=True,
                    torch_dtype=torch.float16,trust_remote_code=False,attn_implementation='eager')
    model.to(device)
    model.config.use_cache=False
    if hasattr(model,'gradient_checkpointing_enable'):
        model.gradient_checkpointing_enable()
    if hasattr(model,'enable_input_require_grads'):
        model.enable_input_require_grads()
    block,params=select_last_block(model)
    if not params:raise RuntimeError('HOLD_NO_DIRECT_TRAINABLE_PARAMETERS')
    baseline_sha=trainable_tensor_digest(params)
    first_eval=mean_holdout_loss(model,tokenizer,device,holdout,args.max_tokens)
    optimizer=torch.optim.AdamW(params,lr=args.lr,betas=(0.9,0.95),weight_decay=0.01)
    scaler=torch.amp.GradScaler('cuda')
    model.train();completed=0;loss_values=[]
    for i in range(args.steps):
        if args.stop_file and pathlib.Path(args.stop_file).exists():break
        optimizer.zero_grad(set_to_none=True)
        loss=item_loss(model,tokenizer,device,train[i%len(train)],args.max_tokens)
        if not torch.isfinite(loss):raise RuntimeError('HOLD_NONFINITE_TRAIN_LOSS')
        scaler.scale(loss).backward()
        scaler.unscale_(optimizer)
        norm=torch.nn.utils.clip_grad_norm_(params,1.0)
        if not torch.isfinite(norm):raise RuntimeError('HOLD_NONFINITE_GRADIENT')
        scaler.step(optimizer)
        scaler.update()
        torch.cuda.synchronize(1)
        completed+=1
        loss_values.append(float(loss.detach().item()))
    after_sha=trainable_tensor_digest(params)
    if completed==0 or after_sha==baseline_sha:
        raise RuntimeError('HOLD_NO_REAL_BASE_WEIGHT_DELTA')
    stage=pathlib.Path(tempfile.mkdtemp(prefix='.nox-v47-staging-',dir=str(out.parent)))
    try:
        # Versioned isolated checkpoint: never modifies live model or S03.
        model.save_pretrained(str(stage),safe_serialization=True,max_shard_size='2GB')
        tokenizer.save_pretrained(str(stage))
        torch.save({'optimizer':optimizer.state_dict(),'scaler':scaler.state_dict(),
                    'steps':completed,'seed':3407,'block':block},str(stage/'optimizer_state.pt'))
        model.eval()
        after_eval=mean_holdout_loss(model,tokenizer,device,holdout,args.max_tokens)
        del model
        gc.collect();torch.cuda.empty_cache()
        reload_model=AutoModelForCausalLM.from_pretrained(str(stage),local_files_only=True,
                   torch_dtype=torch.float16,trust_remote_code=False,attn_implementation='eager').to(device)
        layers_name,params_reload=select_last_block(reload_model)
        reload_sha=trainable_tensor_digest(params_reload)
        if after_sha!=reload_sha or layers_name!=block:
            raise RuntimeError('HOLD_CHECKPOINT_RELOAD_DELTA_MISMATCH')
        test_reload=mean_holdout_loss(reload_model,tokenizer,device,holdout,args.max_tokens)
        if abs(after_eval-test_reload)>0.03:
            raise RuntimeError('HOLD_CHECKPOINT_RELOAD_LOSS_MISMATCH')
        shard_hashes={p.name:sha_file(p) for p in stage.iterdir() if p.is_file()}
        receipt={'schema':'NOX_V47_DIRECT_WEIGHTS_SMOKE','instance_id':'60509551',
                 'utc':dt.datetime.now(dt.timezone.utc).isoformat(),
                 'gpu_index':1,'compute':'V100_SM70_CUDA12_FP16',
                 'trained_layer':block,'optimizer_steps':completed,
                 'direct_base_weights_changed':True,'baseline_layer_sha256':baseline_sha,
                 'after_layer_sha256':after_sha,'reloaded_layer_sha256':reload_sha,
                 'checkpoint_reloaded':True,'holdout_sources_disjoint':True,
                 'baseline_holdout_loss':first_eval,'after_holdout_loss':after_eval,
                 'reload_holdout_loss':test_reload,
                 'quality_gate_passed':(test_reload<=first_eval+0.03),
                 'train_file_sha256':sha_file(args.train),'holdout_file_sha256':sha_file(args.holdout),
                 'checkpoint_files_sha256':shard_hashes,'active_live_model_changed':False,
                 'promotion_authorized':False,'evidence_limit':'1..20 step isolated smoke, not full model distillation'}
        (stage/'NOX_DIRECT_WEIGHTS_RECEIPT.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
        stage.rename(out)
        return {'state':'CHECKPOINT_ISOLATED_REAL_WEIGHTS_SMOKE' if receipt['quality_gate_passed'] else 'HOLD_QUALITY_REGRESSION',
                'steps':completed,'checkpoint':str(out),'receipt':receipt,
                'live_model_changed':False}
    except Exception:
        # Never delete a partially written checkpoint: it may contain the only useful recovery data.
        raise


def main():
    p=argparse.ArgumentParser(description='Real NOX base weights smoke; authorized OneHost only')
    p.add_argument('--student',required=True,help='Vetted local HF trainable weights, NOT GGUF')
    p.add_argument('--train',required=True,help='Audited JSONL prompt/completion/source_uri/rights_verified/privacy_approved')
    p.add_argument('--holdout',required=True,help='Independent source-disjoint JSONL, never used as train')
    p.add_argument('--out',required=True,help='New isolated checkpoint directory, cannot already exist')
    p.add_argument('--steps',type=int,default=1)
    p.add_argument('--max-tokens',type=int,default=192)
    p.add_argument('--lr',type=float,default=5e-6)
    p.add_argument('--stop-file',default='/workspace/nox/STOP')
    p.add_argument('--execute',action='store_true',help='Requires preexisting trusted native approval context')
    a=p.parse_args()
    if not 0<a.lr<=2e-5:raise SystemExit('HOLD_LEARNING_RATE')
    try:r=run(a);print(json.dumps(r,ensure_ascii=False,indent=2))
    except Exception as e:
        print(json.dumps({'state':'HOLD_NO_TRAINING_CLAIM','reason':str(e)[:300],
            'live_model_changed':False,'native_receipt_verified':False},ensure_ascii=False))
        raise SystemExit(2)
if __name__=='__main__':main()
