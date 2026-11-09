#!/usr/bin/env python3
"""NOX REAL-LANGUAGE ADAPTER V1 — inherited 9B frozen backbone, supervised output LoRA.

This does NOT finetune the original 9B matrices or finish S1–S8 layers.
It creates a real cross-entropy trained adapter from actual Qwen3.5-9B
hidden states and preserves source weights, S03, and prior NOX training.
Fail closed under sensor loss, overheating, source mismatch or non-improvement.
"""
from __future__ import annotations
import argparse, ctypes, hashlib, json, math, os, re, shutil, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen, Request

ROOT = Path(r'C:\NOX_HELION\NOX_NEW\brain\prime')
MODEL = ROOT/'models'/'NOX_PRIME_9B_INHERITED'
BRAIN = ROOT.parent
OUT = ROOT/'forge9b'/'real_language_adapter'
SENSOR = 'http://127.0.0.1:8085/data.json'


def sha(p:Path):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(4*1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def write_json(p:Path,d):
    import tempfile
    p.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf8',dir=str(p.parent),delete=False,suffix='.tmp') as f:
        json.dump(d,f,ensure_ascii=False,indent=2);tmp=Path(f.name)
    os.replace(tmp,p)


def sensor():
    with urlopen(Request(SENSOR,headers={'Accept':'application/json'}),timeout=4) as r:
        d=json.load(r)
    readings=[]
    def walk(obj,parent=''):
        if isinstance(obj,list):
            for item in obj:walk(item,parent)
        elif isinstance(obj,dict):
            label=' '.join(str(obj.get(k,'')) for k in ('Text','Name','HardwareName','Identifier'))
            scope=parent+' '+label
            if re.search(r'RX\s*6650\s*M',scope,re.I) and re.search(r'Hot\s*Spot|Hotspot|Junction',label,re.I):
                val=re.search(r'[-+]?\d+(?:[.,]\d+)?',str(obj.get('Value',obj.get('value',''))))
                if not val:raise RuntimeError('SAFE70: Hot Spot value missing')
                readings.append(float(val.group().replace(',','.')))
            for x in obj.values():
                if isinstance(x,(dict,list)):walk(x,scope)
    walk(d)
    if not readings or any(not math.isfinite(x) or not (0<x<120) for x in readings) or max(readings)-min(readings)>3:
        raise RuntimeError('SAFE70: invalid/ambiguous RX6650M Hot Spot')
    return max(readings)


def power():
    if os.name!='nt':return
    class SP(ctypes.Structure):
        _fields_=[('ACLineStatus',ctypes.c_byte),('BatteryFlag',ctypes.c_byte),('BatteryLifePercent',ctypes.c_byte),('SystemStatusFlag',ctypes.c_byte),('BatteryLifeTime',ctypes.c_ulong),('BatteryFullLifeTime',ctypes.c_ulong)]
    x=SP()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(x)):
        raise RuntimeError('POWER_SENSOR_LOST_HOLD')
    if x.ACLineStatus==0 and 0 <= x.BatteryLifePercent < 25:
        raise RuntimeError('BATTERY_HOLD: charge <25%')


def manifest():
    mfile=ROOT/'NOX_PRIME_9B_MANIFEST.json'
    if not mfile.is_file():raise RuntimeError('No inherited 9B manifest')
    m=json.loads(mfile.read_text(encoding='utf8-sig'))
    if m.get('status')!='INHERITED_UNTRAINED' or m.get('source_repository')!='Qwen/Qwen3.5-9B':
        raise RuntimeError('Source 9B lineage mismatch')
    if Path(m.get('model_root','')).resolve()!=MODEL.resolve():
        raise RuntimeError('Original model location mismatch')
    for entry in m['shards']:
        p=MODEL/entry['file']
        if not p.is_file() or p.stat().st_size!=entry['bytes'] or not entry.get('sha256'):
            raise RuntimeError('Original source shard missing/changed: '+str(p))
    return m


def source_data():
    embryo=BRAIN/'NOX_EMBRYO_GENESIS_V1'/'data'
    paths=[embryo/'teacher_experiment.jsonl',embryo/'approved_teacher.jsonl',embryo/'teacher_candidates.jsonl']
    for path in paths:
        if not path.is_file():continue
        rows=[];seen=set()
        for line in path.read_text(encoding='utf8-sig').splitlines():
            if not line.strip():continue
            d=json.loads(line)
            p=str(d.get('prompt','')).strip();a=str(d.get('answer','')).strip()
            if len(p)<10 or len(a)<40 or p in seen:continue
            if d.get('teacher')!='qwen3.5:9b':continue
            if d.get('may_train') is not True and 'candidates' not in str(path):continue
            seen.add(p);rows.append((p,a))
        if len(rows)>=6:return path,rows
    raise RuntimeError('Need >=6 prior 9B teacher prompt-answer examples; no synthetic text generated')


def feature_worker():
    import torch
    from transformers import AutoTokenizer,Qwen3_5ForConditionalGeneration
    m=manifest()
    data_file,rows=source_data()
    # CPU/DISK only, not 8GB DirectML. Disk-offload copies may need ~20GiB.
    cache=OUT/'offload'
    free=shutil.disk_usage(ROOT).free
    if free < 25*1024**3:
        raise RuntimeError('DISK_HOLD: at least 25GiB temporary space required by HF CPU/disk offload (currently %.1fGiB)'%(free/1024**3))
    OUT.mkdir(parents=True,exist_ok=True)
    print('NOX 9B frozen backbone: CPU/DISK offload, original weights IMMUTABLE',flush=True)
    # Accelerate dispatches layers between a bounded CPU budget and disk.
    model=Qwen3_5ForConditionalGeneration.from_pretrained(
        str(MODEL),dtype=torch.bfloat16,low_cpu_mem_usage=True,
        device_map='auto',max_memory={'cpu':'8GiB'},offload_folder=str(cache),
        offload_state_dict=True,attn_implementation='eager',trust_remote_code=False)
    model.requires_grad_(False);model.eval()
    tokenizer=AutoTokenizer.from_pretrained(str(MODEL),trust_remote_code=False)
    head=model.get_output_embeddings()
    if head is None or head.weight.ndim!=2:raise RuntimeError('No genuine Qwen3.5 output embedding found')
    head_name=None
    for name,mod in model.named_modules():
        if mod is head:head_name=name+'.weight';break
    index=json.loads((MODEL/'model.safetensors.index.json').read_text(encoding='utf8-sig'))['weight_map']
    if head_name not in index:
        # Tied head: input embedding matrix is the same tensor.
        inp_emb=model.get_input_embeddings();name_in=None
        for name,mod in model.named_modules():
            if mod is inp_emb:name_in=name+'.weight';break
        if name_in not in index:raise RuntimeError('Output head tensor not found in original 9B shards')
        head_name=name_in
    print('Head source:',head_name,flush=True)
    import numpy as np
    features=[];labels=[];sample_ids=[]
    for n,(question,answer) in enumerate(rows[:8]):
        prompt=f'<|im_start|>user\n{question}<|im_end|>\n<|im_start|>assistant\n'
        p=tokenizer.encode(prompt,add_special_tokens=False)[-20:]
        a=tokenizer.encode(answer,add_special_tokens=False)[:40]
        seq=p+a
        if len(p)<2 or len(a)<6:continue
        x=torch.tensor([seq[:-1]],dtype=torch.long)
        with torch.no_grad():
            out=model(input_ids=x,attention_mask=torch.ones_like(x),output_hidden_states=True,use_cache=False,return_dict=True)
        state=getattr(out,'hidden_states',None)
        if not state or not isinstance(state[-1],torch.Tensor):
            raise RuntimeError('NOX HOLD: Qwen3.5 API did not return final language hidden state')
        h=state[-1].detach().float().cpu().numpy()[0]
        if h.shape[0]!=len(seq)-1 or h.shape[1]!=head.weight.shape[1]:
            raise RuntimeError('Hidden-state dimension mismatch')
        for j in range(len(p)-1,len(seq)-1):
            features.append(h[j]);labels.append(seq[j+1]);sample_ids.append(n)
        print('Language features from Qwen3.5-9B example',n+1,'/',min(8,len(rows)),flush=True)
    if len(features)<16:raise RuntimeError('Insufficient supervised Qwen3.5 language positions')
    feats=np.asarray(features,dtype=np.float32)
    lab=np.asarray(labels,dtype=np.int64)
    ids=np.asarray(sample_ids,dtype=np.int32)
    np.savez_compressed(OUT/'qwen9b_hidden_teacher_forced.npz',features=feats,labels=lab,samples=ids)
    write_json(OUT/'feature_provenance.json',{'source_revision':m['source_revision'],
       'dataset_sha256':sha(data_file),'head_key':head_name,'head_shard':index[head_name],
       'feature_count':len(features),'example_count':len(set(sample_ids)),
       'objective':'true next token CE on inherited 9B hidden states',
       'note':'Frozen 9B backbone; trainable final output residual adapter, not 9B parameter finetune.'})
    print('NOX_9B_FEATURES_REAL',len(features),flush=True)


def gpu_worker():
    import torch,torch_directml,numpy as np
    from safetensors import safe_open
    from safetensors.torch import save_file,load_file
    provenance=json.loads((OUT/'feature_provenance.json').read_text(encoding='utf8'))
    m=manifest()
    if provenance.get('source_revision')!=m['source_revision']:raise RuntimeError('Feature/model revision mismatch')
    arr=np.load(OUT/'qwen9b_hidden_teacher_forced.npz',allow_pickle=False)
    X=torch.tensor(arr['features'],dtype=torch.float32)
    Y=torch.tensor(arr['labels'],dtype=torch.long)
    groups=arr['samples']
    n=int(max(groups))+1
    if n<6:raise RuntimeError('Insufficient independent examples')
    train_idx=[i for i,v in enumerate(groups) if v<n-2]
    val_idx=[i for i,v in enumerate(groups) if v>=n-2]
    if len(train_idx)<8 or len(val_idx)<4:raise RuntimeError('Insufficient train/validation positions')
    device=torch_directml.device()
    with safe_open(str(MODEL/provenance['head_shard']),framework='pt',device='cpu') as f:
        head_cpu=f.get_tensor(provenance['head_key'])
    hidden=int(X.shape[1]);vocab=int(head_cpu.shape[0])
    if head_cpu.shape[1]!=hidden or vocab<100000:raise RuntimeError('Original full LM head dimensions unexpected')
    # The full 248K-class genuine LM head stays on CPU (~4GiB float32).
    # CPU computes exact cross-entropy and dLoss/dHidden. Only the two low-rank
    # matrices and their optimizer are on AMD DirectML. This avoids a fake
    # 8GB-VRAM full-model training claim and unsupported huge DML softmax.
    torch.set_num_threads(4)
    head=head_cpu.float().contiguous()
    del head_cpu
    rank=4;scale=2.0
    A=torch.nn.Parameter(torch.randn(rank,hidden,device=device,dtype=torch.float32)*0.003)
    B=torch.nn.Parameter(torch.zeros(hidden,rank,device=device,dtype=torch.float32))
    opt=torch.optim.AdamW([A,B],lr=0.0005,weight_decay=0.0)
    def evaluate(indices):
        with torch.no_grad():
            vals=[]
            for i in range(0,len(indices),2):
                chosen=indices[i:i+2]
                xi=X[chosen].to(device)
                delta=((xi@A.T)@B.T)*scale
                hidden_cpu=X[chosen]+delta.detach().cpu()
                logits=hidden_cpu @ head.T
                val=torch.nn.functional.cross_entropy(logits,Y[chosen])
                vals.append(float(val.detach().cpu()))
            return sum(vals)/len(vals)
    torch.manual_seed(764)
    before=evaluate(val_idx)
    init_a=A.detach().cpu().clone();init_b=B.detach().cpu().clone()
    best_val=before;best=None;best_step=0
    print('NOX 9B language learning: real frozen LM head',vocab,'classes on CPU, DirectML',device,'validation_before',before,flush=True)
    for step in range(32):
        chosen=train_idx[(step*2)%len(train_idx):(step*2)%len(train_idx)+2]
        xi=X[chosen].to(device)
        delta=((xi@A.T)@B.T)*scale
        # Exact genuine language loss on tokens, not a fabricated matrix target.
        hidden_cpu=(X[chosen]+delta.detach().cpu()).requires_grad_(True)
        logits=hidden_cpu @ head.T
        loss=torch.nn.functional.cross_entropy(logits,Y[chosen])
        if not bool(torch.isfinite(loss.detach())):raise RuntimeError('Non-finite CPU language loss')
        loss.backward()
        grad_hidden=hidden_cpu.grad
        if grad_hidden is None or not bool(torch.isfinite(grad_hidden).all()):
            raise RuntimeError('Missing genuine 9B language-loss gradient')
        # ∂Loss/∂LoRA = ∂LoRA/∂hidden · ∂Loss/∂hidden; exact chain rule.
        opt.zero_grad(set_to_none=True)
        surrogate=(delta*grad_hidden.detach().to(device)).sum()
        surrogate.backward()
        grad=B.grad
        if grad is None or not bool(torch.isfinite(grad).all().cpu().item()):
            raise RuntimeError('DirectML LoRA backward invalid')
        if float(grad.detach().float().cpu().norm())<=0:
            raise RuntimeError('DirectML LoRA gradient is zero')
        torch.nn.utils.clip_grad_norm_([A,B],1.0)
        opt.step()
        if (step+1)%4==0:
            val=evaluate(val_idx)
            print(f'NOX REAL GPU {step+1}/32 train_loss={float(loss.detach().cpu()):.4f} val={val:.4f}',flush=True)
            if val<best_val-1e-5:
                best_val=val;best_step=step+1;best={'A':A.detach().cpu().clone().contiguous(),'B':B.detach().cpu().clone().contiguous()}
    if best is None:raise RuntimeError('NO_GAIN_HOLD: GPU optimizer ran, but held-out language loss did not improve')
    if torch.equal(init_a,best['A']) or torch.equal(init_b,best['B']):raise RuntimeError('NO_DELTA_HOLD: adapter weights unchanged')
    OUT.mkdir(parents=True,exist_ok=True)
    path=OUT/'NOX_9B_S8_OUTPUT_ADAPTER.safetensors'
    tmp=OUT/'NOX_9B_S8_OUTPUT_ADAPTER.tmp.safetensors'
    save_file(best,str(tmp),metadata={'status':'EXPERIMENTAL_LANGUAGE_ADAPTER','train_source':'Qwen3.5-9B frozen','independent_quality_evaluation':'false'})
    disk=load_file(str(tmp))
    if not all(torch.equal(disk[k],v) for k,v in best.items()):raise RuntimeError('Adapter serialization mismatch')
    os.replace(tmp,path)
    record={'status':'EXPERIMENTAL_LANGUAGE_ADAPTER_TRAINED','source_revision':m['source_revision'],
       'adapter':'output_residual_lora_rank4','scope':'post_last_text_layer_and_before_lm_head',
       'genuine_9b_language_hidden_states':True,'9b_original_weights_modified':False,
       'gpu_backend':str(device),'optimizer_steps':best_step,'attempted_steps':32,
       'heldout_loss_before':before,'heldout_loss_after':best_val,
       'adapter_file':str(path),'sha256':sha(path),'independent_skill_pass':False,
       'data_quality':'EXPERIMENTAL_8_PREVIOUS_TEACHER_EXAMPLES',
       'timestamp_utc':datetime.now(timezone.utc).isoformat()}
    write_json(OUT/'NOX_9B_S8_OUTPUT_ADAPTER_RECEIPT.json',record)
    print('NOX_REAL_LANGUAGE_ADAPTER_TRAINED',json.dumps(record,ensure_ascii=False),flush=True)


def supervise(cpu_python,gpu_python):
    manifest();source_data();power()
    # Do not alter source 9B model, existing NOX or its S03.
    for i in range(3):
        t=sensor()
        if t>=75:raise RuntimeError('SAFE70_HARD_STOP')
        print(f'NOX SAFE70 preflight {i+1}/3: {t:.1f} C',flush=True)
        time.sleep(2)
    operations=[('PREPARING_9B_LANGUAGE_FEATURES',[str(cpu_python),str(Path(__file__).resolve()),'--feature-worker']),
                ('TRAINING_RX6650M_LANGUAGE_ADAPTER',[str(gpu_python),str(Path(__file__).resolve()),'--gpu-worker'])]
    for label,cmd in operations:
        print('NOX',label,flush=True)
        proc=subprocess.Popen(cmd,cwd=str(ROOT),creationflags=getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0))
        high=0
        try:
            while proc.poll() is None:
                t=sensor();power()
                print(f'NOX GPU Hot Spot {t:.1f}C | {label}',flush=True)
                if t>=75:raise RuntimeError('SAFE70_HARD_STOP >=75C')
                high=high+1 if t>=70 else 0
                if high>=3:raise RuntimeError('SAFE70_THREE_CONSECUTIVE >=70C')
                time.sleep(2)
            if proc.returncode!=0:raise RuntimeError(f'{label} HOLD exit={proc.returncode}')
        except BaseException:
            if proc.poll() is None:
                if os.name=='nt':subprocess.run(['taskkill','/F','/T','/PID',str(proc.pid)],capture_output=True)
                else:proc.kill()
            raise
    print('NOX REAL 9B LANGUAGE ADAPTER: VERIFIED GPU RECEIPT (not full 9B finetuning)',flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--feature-worker',action='store_true');p.add_argument('--gpu-worker',action='store_true');p.add_argument('--cpu-python');p.add_argument('--gpu-python')
    a=p.parse_args()
    try:
        if a.feature_worker:feature_worker()
        elif a.gpu_worker:gpu_worker()
        else:supervise(a.cpu_python,a.gpu_python)
        return 0
    except Exception as e:
        print('NOX HOLD:',str(e),file=sys.stderr,flush=True)
        return 1
if __name__=='__main__':sys.exit(main())